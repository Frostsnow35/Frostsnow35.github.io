---
title: "xv6实验-COW"
date: 2026-07-16T13:08:52.108124+00:00
category: "技术"
tags: ["OS", "xv6", "笔记"]
excerpt: "xv6实验 lab - COW笔记"
readTime: 20
legacyId: 3
---

## 一、 宏观视野与核心理念

### 1. 什么是 COW？为什么需要它？

在传统的fork()函数中，子进程会完全拷贝父进程的物理内存。但fork()后通常会紧跟着exec()（加载新程序），之前的拷贝就白费了；或者父子进程只需要读同一块内存。拷贝内存非常耗时。 **COW (Copy-on-Write, 写时复制)** 的理念是：**惰性求值**。 fork() 时，让子进程和父进程共享同一块物理内存，并将这些页面的权限设为**只读**。只有当其中一方尝试写入时，操作系统才触发异常，这时才真正去复制那一页（注意是一页，不是整个内存）。

### 2. COW 机制的系统性架构

为了实现 COW，我们将整个系统划分为四个逻辑层进行改造：

1. **物理内存管理层 (**`kalloc.c`**)**：建立物理页引用计数机制，确保共享页不被过早释放。
2. **虚拟内存映射层 (**`vm.c` **-** `uvmcopy`**)**：在 `fork()` 时放弃深度拷贝，改为共享映射并降权只读。
3. **异常处理层 (**`trap.c` **-** `usertrap`**)**：捕获写只读页引发的硬件异常，在此刻执行真正的复制。
4. **内核数据写入层 (**`vm.c` **-** `copyout`**)**：填补内核态写入用户态 COW 页不触发异常的漏洞。

## 二、 核心实现步骤与原理解析 (含关键代码)

### 步骤 1：物理页引用计数 (`kernel/kalloc.c`)

**理念**：谁分配，谁计数；谁引用，谁递增。解决“共享物理页何时真正回收”的问题。

- **数据结构**：定义全局数组，用物理地址除以页大小作为下标，实现 O(1) 查找。

  ```c
  struct {
    struct spinlock lock;
    int count[(uint64)PHYSTOP / PGSIZE]; 
  } ref_count;
  ```

- **辅助函数**：`decref` 返回当前计数值，由调用者决定是否真正释放物理页（避免锁顺序倒置导致的死锁）。

  ```c
  void incref(uint64 pa) {
    acquire(&ref_count.lock);
    ref_count.count[pa / PGSIZE]++;
    release(&ref_count.lock);
  }
  
  int decref(uint64 pa) {
    int count_val;
    acquire(&ref_count.lock);
    ref_count.count[pa / PGSIZE]--;
    count_val = ref_count.count[pa / PGSIZE];
    release(&ref_count.lock);
    return count_val;
  }
  ```

- **初始化的问题**：`freerange` 初始化内存时调用 `kfree`，但此时计数全为 0。解决：在调用 `kfree` 前，显式将计数设为 1。

  ```c
  void freerange(void *pa_start, void *pa_end) {
    char *p;
    p = (char*)PGROUNDUP((uint64)pa_start);
    for(; p + PGSIZE <= (char*)pa_end; p += PGSIZE) {
      ref_count.count[(uint64)p / PGSIZE] = 1; // 预设为 1
      kfree(p);
    }
  }
  ```

- `kalloc` **与** `kfree` **修改**：

  ```c
  void *kalloc(void) {
    // ... 获取 r 并从 freelist 移除 ...
    if(r) {
      release(&kmem.lock);
      memset((char*)r, 5, PGSIZE); 
      incref((uint64)r); // 分配时引用设为 1
      return (void*)r;
    }
    // ...
  }
  
  void kfree(void *pa) {
    // ... 合法性检查 ...
    if (decref((uint64)pa) > 0) {
      return; // 还有别人在用，不释放
    }
    // 引用归 0，真正释放回 freelist
    memset(pa, 1, PGSIZE);
    r = (struct run*)pa;
    acquire(&kmem.lock);
    r->next = kmem.freelist;
    kmem.freelist = r;
    release(&kmem.lock);
  }
  ```

### 步骤 2：COW 映射 (`kernel/riscv.h` & `kernel/vm.c`)

**理念**：共享代替复制，标记代替执行。

- **定义标志位**：在 `riscv.h` 中利用 RISC-V PTE 的保留位定义 `PTE_COW`。

  ```c
  #define PTE_COW (1L << 8) // 1L << 8 表示将第 8 位置 1 (RSW 位 reserved for OS)
  ```

- **修改** `uvmcopy` **逻辑**：遍历父进程页表，清除父子进程的写权限，打上 COW 标记，共享物理地址，增加引用计数。

  ```c
  int uvmcopy(pagetable_t old, pagetable_t new, uint64 sz) {
    pte_t *pte;
    uint64 pa, i;
    uint flags;
    for(i = 0; i < sz; i += PGSIZE){
      if((pte = walk(old, i, 0)) == 0) panic("uvmcopy: pte should exist");
      if((*pte & PTE_V) == 0) panic("uvmcopy: page not present");
      
      pa = PTE2PA(*pte);
      if(*pte & PTE_W) {
        *pte = (*pte & ~PTE_W); // 清除父进程 PTE_W
        *pte = (*pte | PTE_COW); // 打上 PTE_COW
      }
      incref(pa); // 子进程也要指向它
      flags = PTE_FLAGS(*pte); // 子进程继承修改后的 flags
      
      if(mappages(new, i, PGSIZE, (uint64)pa, flags) != 0) goto err;
    }
    return 0;
  err:
    uvmunmap(new, 0, i / PGSIZE, 1);
    return -1;
  }
  ```

### 步骤 3：捕获 Page Fault (`kernel/trap.c`)

**理念**：硬件与软件的契约。硬件负责拦截越权，软件负责核对并补救。

- 在 `usertrap` 中拦截 `scause == 15` (Store Page Fault)。

  ```c
  } else if(r_scause() == 15) {
    uint64 va = r_stval();
    if(cowfault(p->pagetable, va) != 0) {
      p->killed = 1; // 如果 cowfault 失败，杀掉进程
    }
  } else if((which_dev = devintr()) != 0){
  ```

- `cowfault` **核心逻辑**：

  ```c
  int cowfault(pagetable_t pagetable, uint64 va) {
    if(va >= MAXVA) return -1;
    uint64 va_aligned = PGROUNDDOWN(va);
    pte_t *pte = walk(pagetable, va_aligned, 0);
    if(pte == 0 || (*pte & PTE_V) == 0 || (*pte & PTE_COW) == 0) return -1;
  
    uint64 old_pa = PTE2PA(*pte);
    uint64 new_pa = (uint64)kalloc();
    if(new_pa == 0) return -1;
    
    memmove((void*)new_pa, (void*)old_pa, PGSIZE);
    kfree((void*)old_pa); // 释放对旧页的引用
  
    uint flags = PTE_FLAGS(*pte);
    flags = (flags | PTE_W) & ~PTE_COW; // 加写权限，去 COW 标记
    *pte = PA2PTE(new_pa) | flags;
    return 0;
  }
  ```

### 步骤 4：填补内核陷阱 (`kernel/vm.c` - `copyout`)

**理念**：内核态不受硬件页保护机制的限制，必须手动检查。否则会导致管道等机制崩溃。

- 在 `copyout` 执行拷贝前，手动触发 COW。

  ```c
  int copyout(pagetable_t pagetable, uint64 dstva, char *src, uint64 len) {
    uint64 n, va0, pa0;
    while(len > 0){
      va0 = PGROUNDDOWN(dstva);
      
      // --- 手动处理 COW 页 ---
      if(va0 < MAXVA) {
          pte_t *pte = walk(pagetable, va0, 0);
          if(pte != 0 && (*pte & PTE_V) && (*pte & PTE_COW)) {
              if(cowfault(pagetable, va0) != 0) return -1;
          }
      }
      // -----------------------
      pa0 = walkaddr(pagetable, va0);
      if(pa0 == 0) return -1;
      // ... 后续正常拷贝逻辑 ...
  ```

## 三、 性能基准测试与极致优化 (Optional Challenge)

### 1. 测量工具构建

- 编写 `user/cowbench.c`：分配 1000 页 (4MB)，`fork` 后子进程遍历修改所有页触发 COW。
- 添加 `get_kalloc_count` 系统调用：贯穿 `kalloc.c`、`sysproc.c`、`syscall.c`、`user.h`，记录全局 `kalloc` 调用次数。

### 2. 基线数据 vs 优化数据对比

让父进程在子进程写入前提前退出（不调用 `wait`），使得共享物理页的引用计数降为 1。

测试阶段耗时Kalloc 调用次数 (扣除系统开销)现象分析：

**优化前**1 tick1007 (1000次 cowfault 分配) 即使没有其他进程共享了，子进程写入时依然要分配新页、拷贝数据、释放旧页。

**优化后**1 tick**7 (0次 cowfault 分配)** `cowfault` 发现引用计数为 1，直接夺回写权限，0 次分配，0 次拷贝

### 3. 极致优化原理：“最后写入者优化”

在 `cowfault` 分配新页前，增加判断逻辑：

```c
if (get_ref(old_pa) == 1) {
    *pte = (*pte | PTE_W) & ~PTE_COW; // 原地解除 COW，恢复写权限
    return 0; // 0 次分配，0 次拷贝
}
```

**效果**：当其他共享者已经退出时，当前进程成为这页内存的“最后守护者”，无需再做无用的数据搬移，实现对系统资源精细的掌控。

## 四、 踩坑记录

1. **C 语言编译的严苛性**
   - *报错*：`implicit declaration of function`、`comparison between pointer and integer`、`unused variable`。
   - *方法*：C 语言从上往下编译，跨文件调用必须有前置声明 (`defs.h`)；严格区分指针和整数类型 (`uint64`强转)；内核级编译常开启 `-Werror`，不容忍废弃变量。
2. **系统调用添加的规范性**
   - *报错*：`multiple definition` / `undefined reference`。
   - *方法*：严格区分底层逻辑函数（在 `kalloc.c` 中实现）和系统调用接口（在 `sysproc.c` 中实现，以 `sys_` 为前缀）。保证 `defs.h` 中声明的纯净性。
3. **并发与锁的秩序**
   - *隐藏陷阱*：在 `decref` 中如果持有 `ref_count.lock` 同时去获取 `kmem.lock` 释放内存，极易死锁。
   - *方法*：锁的粒度要小，获取时间要短。`decref` 只管减计数并返回结果，由调用者决定是否调用 `kfree` 获取另一把锁。
4. **系统闭环思维**
   - *隐藏陷阱*：`copyout` 不处理 COW 导致 `pipe()` 崩溃。
   - *方法*：在修改底层虚拟内存机制时，必须审视所有直接操作物理/虚拟内存的路径。用户态靠硬件中断拦截，内核态必须靠代码手动拦截，二者缺一不可。

## 总结

COW体现了现代操作系统在“虚拟内存”、“异常处理”和“进程隔离”之间的精妙协作。性能测试和极致优化体现了系统设计中的“懒加载”理念的优势。

---
title: "xv6-mmap"
date: 2026-07-30T15:13:41.723269+00:00
category: "技术"
tags: ["xv6", "os"]
excerpt: "6.1810 2025 fall Labs mmap"
readTime: 36
legacyId: 15
---

## 一、实验目标

为 xv6 添加 `mmap` 和 `munmap` 系统调用，实现文件到进程地址空间的**内存映射**。核心要求：

- `mmap` 采用**懒加载**策略：调用时只记录元数据（VMA），不分配物理内存也不读取文件。真正的页面分配和文件读取发生在缺页异常（Page Fault）处理中。
- `munmap` 解除映射，MAP_SHARED 区域需要将脏页**写回文件**。
- 进程 `exit` 时自动清理所有映射区域（等同于隐式 munmap）。
- `fork` 时子进程继承父进程的 VMA 表。

最终 `mmaptest` 全部通过，`usertests -q` 正常工作。

---

## 二、源码分析

### 2.1 关键数据结构

#### VMA（Virtual Memory Area）

定义在 [kernel/proc.h](file:///e:/tmp/xv6-labs-2025/kernel/proc.h#L86-L93)：

```c
#define NVMA 16

struct vma {
  uint64 addr;      // 映射起始虚拟地址（页对齐）
  uint64 len;       // 映射总长度（字节，页对齐）
  int prot;         // 访问权限：PROT_READ / PROT_WRITE
  int flags;        // 映射类型：MAP_SHARED / MAP_PRIVATE
  struct file *file;// 关联的文件指针
  uint64 offset;    // 文件内起始偏移（本实验恒为 0）
};
```

每个进程在 `struct proc` 中嵌入固定大小的 VMA 数组 `struct vma vmas[NVMA]`。

#### RISC-V Sv39 页表项（PTE）位定义

定义在 [kernel/riscv.h](file:///e:/tmp/xv6-labs-2025/kernel/riscv.h#L358-L364)：

| 位 | 宏    | 含义                            |
| -- | ----- | ------------------------------- |
| 0  | PTE_V | 页表项有效（Valid）             |
| 1  | PTE_R | 可读（Read）                    |
| 2  | PTE_W | 可写（Write）                   |
| 3  | PTE_X | 可执行（Execute）               |
| 4  | PTE_U | 用户态可访问（User）            |
| 7  | PTE_D | 脏页标志（Dirty），硬件自动维护 |

PTE_D 是 RISC-V 规范定义的标准位：当 CPU 执行 store 指令写入页面时，硬件自动将该位置 1。操作系统通过读取它来判断页面是否被修改过。

### 2.2 数据流分析

整个 mmap 系统涉及以下组件协作：

```
用户态调用 mmap()
    ↓ syscall (trampoline)
sys_mmap()                  [kernel/sysproc.c]
    → 分配 VMA 槽位
    → 分配虚拟地址（从 0x60000000 向下增长）
    → filedup(f) 增加文件引用计数
    → 返回虚拟地址给用户
    ↓ (不分配物理页，不读文件)

用户访问映射区域 → Page Fault (scause=13/15)
    ↓
usertrap()                  [kernel/trap.c]
    → 识别 scause == 13 (Load) 或 15 (Store)
    → 调用 vmfault(pagetable, stval, read)
        ↓
vmfault()                   [kernel/vm.c]
    → 判断 fault_addr 位置：
      ├── fault_addr < p->sz → 堆懒分配
      └── fault_addr >= p->sz → find_vma() 查找 VMA
          → kalloc() 分配物理页
          → memset 清零
          → readi() 从文件读取 4096 字节
          → mappages() 建立虚拟地址到物理页的映射
          → 返回物理地址

用户调用 munmap()
    ↓ syscall
sys_munmap()                [kernel/sysproc.c]
    → find_vma() 查找对应 VMA
    → MAP_SHARED: 遍历页面，检查 PTE_D
      → writei() 写回脏页（限制不超过原文件大小）
    → uvmunmap() 解除页表映射，释放物理页
    → 更新/删除 VMA
```

### 2.3 freewalk 的契约

`freewalk` 是释放页表树的递归函数，其前置条件是：**所有叶子映射必须已通过 `uvmunmap` 清除**。若遇到有效的叶子 PTE（PTE_V 且 PTE_R/W/X 之一置位），直接 `panic("freewalk: leaf")`。这是一个防御性设计，防止内存泄漏和 use-after-free。

`uvmfree` 的调用流程：

```
uvmfree(pagetable, sz)
    → uvmunmap(pagetable, 0, PGROUNDUP(sz)/PGSIZE, do_free=1)  // 按 p->sz 清理堆区域
    → freewalk(pagetable)  // 释放页表页，此时不应再有残留叶子 PTE
```

---

## 三、实现思路

### 3.1 总体策略

遵循 xv6 的"最小充分实现"原则：

1. `mmap` 不分配物理页 —— 只填充 VMA 元数据
2. 缺页时按需读文件 —— 在 `vmfault` 中处理 mmap 区域的缺页
3. `munmap` 负责清理 —— 写回脏页、释放物理页、释放文件引用
4. `exit` 兜底清理 —— 进程退出时清理所有残留 VMA
5. `fork` 继承 VMA —— 子进程复制 VMA 表并增加文件引用计数

### 3.2 地址空间布局

采用从高地址向下增长的策略，将 mmap 区域放在堆的上方：

```
┌─────────────────┐ MAXVA (0x40000000000)
│   TRAMPOLINE    │
├─────────────────┤
│   TRAPFRAME     │
├─────────────────┤
│                 │
│   mmap 区域     │ ← 从 0x60000000 向下增长
│   (懒加载页面)  │
├─────────────────┤
│   堆 (heap)     │ ← p->sz 管理，向上增长
├─────────────────┤
│   用户栈        │
├─────────────────┤
│   代码/数据     │
└─────────────────┘ 0x0
```

### 3.3 文件写回的 POSIX 语义

关键规则：**MAP_SHARED 写回时不能扩展文件**。超过原文件大小的写入只存在于内存中，不反映到磁盘。

实现方式：在写回前加锁读取 `ip->size`，只写入 `min(PGSIZE, ip->size - file_offset)` 字节。若 `file_offset >= ip->size` 则整页跳过写回。

### 3.4 权限检查

- `mmap` 时：MAP_SHARED + PROT_WRITE 要求文件以可写方式打开
- `vmfault` 时：当触发写缺页（scause=15, read=0）但 VMA 未设置 PROT_WRITE 时，拒绝处理并返回 0（进程被杀死）

---

## 四、实际变动内容

### 4.1 分支初始状态（已存在的代码）

| 文件                                                                                                                                                  | 已有内容                                                                          |
| ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [kernel/proc.h](file:///e:/tmp/xv6-labs-2025/kernel/proc.h#L84-L118)                                                                                   | VMA 结构体定义、NVMA=16、`struct vma vmas[NVMA]`                                |
| [kernel/fcntl.h](file:///e:/tmp/xv6-labs-2025/kernel/fcntl.h#L10-L15)                                                                                  | PROT_READ, PROT_WRITE, MAP_SHARED, MAP_PRIVATE 宏定义                             |
| [kernel/defs.h](file:///e:/tmp/xv6-labs-2025/kernel/defs.h#L1-L4)                                                                                      | LAB_MMAP 下的 size_t/off_t 类型定义                                               |
| [kernel/defs.h](file:///e:/tmp/xv6-labs-2025/kernel/defs.h#L111)                                                                                       | `find_vma` 声明                                                                 |
| [kernel/defs.h](file:///e:/tmp/xv6-labs-2025/kernel/defs.h#L188-L189)                                                                                  | `ismapped`, `vmfault` 声明                                                    |
| [kernel/syscall.c](file:///e:/tmp/xv6-labs-2025/kernel/syscall.c#L105-L106) / [kernel/syscall.h](file:///e:/tmp/xv6-labs-2025/kernel/syscall.h#L24-L25) | SYS_mmap(23), SYS_munmap(24) 条目                                                 |
| [kernel/proc.c](file:///e:/tmp/xv6-labs-2025/kernel/proc.c#L689-L702)                                                                                  | `find_vma` 函数                                                                 |
| [kernel/vm.c](file:///e:/tmp/xv6-labs-2025/kernel/vm.c#L457-L549)                                                                                      | 含 mmap 分支的`vmfault`、`ismapped`、`copyin`/`copyout` 中的 vmfault 回退 |
| [kernel/trap.c](file:///e:/tmp/xv6-labs-2025/kernel/trap.c#L66-L73)                                                                                    | usertrap 中缺页异常处理                                                           |
| [kernel/sysproc.c](file:///e:/tmp/xv6-labs-2025/kernel/sysproc.c#L109-L174)                                                                            | 完整的`sys_mmap` 实现                                                           |
| [kernel/sysproc.c](file:///e:/tmp/xv6-labs-2025/kernel/sysproc.c#L176-L180)                                                                            | `sys_munmap` 空壳（`return -1`）                                              |

### 4.2 本次修改的文件

#### [kernel/riscv.h](file:///e:/tmp/xv6-labs-2025/kernel/riscv.h#L364)

新增 `PTE_D` 宏定义：

```c
#define PTE_D (1L << 7) // dirty
```

#### [kernel/sysproc.c](file:///e:/tmp/xv6-labs-2025/kernel/sysproc.c) — sys_mmap 权限检查 + sys_munmap 完整实现

**新增头文件引用**（L9-L10）：

```c
#include "sleeplock.h"
#include "fs.h"
```

**mmap 权限检查**（L138-L140，在基础合法性检查之后）：

```c
// MAP_SHARED + PROT_WRITE 要求文件可写
if((prot & PROT_WRITE) && (flags & MAP_SHARED) && !f->writable)
    return -1;
```

**munmap 完整实现**（L176-L248），从空壳替换为完整逻辑：

- 参数校验（地址对齐、长度合法）
- find_vma 定位 VMA
- MAP_SHARED 脏页写回（遍历页面检查 PTE_D，限制写入量不超过文件大小）
- `uvmunmap` 解除映射并释放物理页
- VMA 更新/删除（支持头部 unmap、尾部 unmap、完整 unmap）

#### [kernel/proc.c](file:///e:/tmp/xv6-labs-2025/kernel/proc.c) — kexit VMA 清理 + kfork VMA 复制 + 头文件

**新增头文件引用**（L6-L12）：

```c
#include "sleeplock.h"  // struct sleeplock
#include "fs.h"         // NDIRECT
#include "fcntl.h"      // MAP_SHARED, MAP_PRIVATE
#include "file.h"       // struct file
```

**kexit VMA 清理**（L342-L365），在关闭文件描述符之前：

- 遍历所有 VMA
- MAP_SHARED 时遍历页面写回脏页（同样限制不超过文件大小）
- `uvmunmap` 解除映射并释放物理页
- `fileclose` 释放文件引用

**kfork VMA 复制**（L291-L298），在 `filedup` 文件描述符之后：

```c
for(i = 0; i < NVMA; i++){
    if(p->vmas[i].len > 0){
        np->vmas[i] = p->vmas[i];
        filedup(np->vmas[i].file);
    }
}
```

---

## 五、遇到的问题、原因诊断与解决方案

### 问题 1：`panic: freewalk: leaf`

**现象**：

```
mmaptest failure: munmap (1), pid=3
panic: freewalk: leaf
```

**调用链**：

```
munmap 返回 -1 → mmaptest 调用 exit(1)
  → kexit() → 进程变 ZOMBIE
    → freeproc() → proc_freepagetable(pagetable, p->sz)
      → uvmfree(pagetable, 0x7000)
        → uvmunmap(0, 7, do_free=1)  // 只清理 [0x0, 0x7000)
        → freewalk(pagetable)
          → 发现 L2 页表项仍指向 mmap 页面的叶子 PTE
          → panic("freewalk: leaf")
```

**根因**：

两个问题叠加：

1. `sys_munmap` 是空壳（`return -1`），无法工作
2. `kexit` 没有清理 VMA 区域。`uvmfree` 按 `p->sz` 的边界清理堆内存，而 mmap 懒加载的页面在 0x5fffe000 附近，远在 `p->sz`（0x7000）范围之外。这些页面留在页表中未被 `uvmunmap` 清除，导致 `freewalk` 遇到残留的叶子 PTE 并 panic。

**解决方案**：

- 实现 `sys_munmap`：VMA 查找 → 脏页写回 → uvmunmap → VMA 更新
- 在 `kexit` 中添加 VMA 清理循环：脏页写回 → uvmunmap → fileclose

### 问题 2：编译错误 — 缺失类型和宏定义

**现象**：

```
error: 'MAP_SHARED' undeclared
error: 'PTE_D' undeclared
error: invalid use of undefined type 'struct file'
error: field 'lock' has incomplete type (struct sleeplock)
error: 'NDIRECT' undeclared
```

**根因**：`proc.c` 和 `sysproc.c` 原本不操作文件系统和 VMA 中的文件字段，因此在 `kexit` 和 `sys_munmap` 新增的写回逻辑中引用了未包含的类型和宏。

**解决方案**：

- `riscv.h` 新增 `#define PTE_D (1L << 7)`
- `proc.c` 和 `sysproc.c` 新增 `#include`：
  - `"sleeplock.h"` — 提供 `struct sleeplock`
  - `"fs.h"` — 提供 `NDIRECT`
  - `"fcntl.h"` — 提供 `MAP_SHARED`, `MAP_PRIVATE`
  - `"file.h"` — 提供 `struct file` 的完整定义

### 问题 3：`test mmap read-only` 失败 — mmap(3)

**现象**：

```
test mmap read-only
mmaptest failure: mmap (3), pid=3
```

**测试逻辑**：

```c
fd = open(f, O_RDONLY);  // 只读打开文件
p = mmap(0, PGSIZE*2, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
if (p != MAP_FAILED) err("mmap (3)");  // 期望 mmap 失败
```

**根因**：`sys_mmap` 缺少对文件可写性和映射标志的交叉检查。对只读文件做 MAP_SHARED + PROT_WRITE 映射应当被拒绝（因为共享写入必然需要写回文件），但代码没有检查。

**解决方案**：在 `sys_mmap` 的基础合法性检查之后添加：

```c
if((prot & PROT_WRITE) && (flags & MAP_SHARED) && !f->writable)
    return -1;
```

注意：MAP_PRIVATE + PROT_WRITE 对只读文件是允许的（因为 PRIVATE 写入不会回写到磁盘）。

### 问题 4：`test mmap dirty` 失败 — dirty read #2

**现象**：

```
test mmap dirty
mmaptest failure: dirty read #2, pid=3
```

**测试逻辑**：

```c
// 文件只有 1.5 页（6144 字节），mmap 了 3 页
fd = open(f, O_RDWR);
p = mmap(0, PGSIZE*3, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
// 写 'B' 到第 0 页，写 'C' 到第 1 页
munmap(p, PGSIZE*2);  // 写回前两页
// 重新打开文件验证
read(fd, buf, PGSIZE);       // 期望 4096 字节 ← 通过
read(fd, buf, PGSIZE);       // 期望 2048 字节 ← 失败（实际返回 4096）
```

**根因**：写回第 1 页时，`writei(ip, 0, pa, 4096, PGSIZE)` 向文件偏移 4096 写入了整页 4096 字节，把文件从 6144 字节扩展到了 8192 字节。第二次 `read` 实际读到了 4096 字节而不是预期的 2048 字节。

更深层的原因：POSIX 规定 mmap MAP_SHARED 写回**不能扩展文件**。超过文件末尾的写入只存在于内存中。

**解决方案**：在写回脏页前，加锁读取 `ip->size`，只写入 `min(PGSIZE, ip->size - file_offset)` 字节。若 `file_offset >= ip->size`，整页跳过写回。此修改同时应用于 `sys_munmap` 和 `kexit` 两处。

---

## 六、关键操作系统知识点

1. **懒加载（Demand Paging）**：mmap 不在调用时分配物理内存，而是在缺页异常中按需分配。这保证了 mmap 大文件的快速响应，并允许映射大于物理内存的文件。
2. **RISC-V 页表 Dirty Bit（PTE_D）**：硬件自动维护。CPU 执行 store 指令时自动将该位置 1。操作系统利用它精确追踪哪些页面被修改过，避免无意义的磁盘写回。这是实现 Copy-on-Write 和 mmap 写回的基础机制。
3. **文件引用计数（Reference Counting）**：`filedup` 和 `fileclose` 维护 `struct file` 的引用计数。mmap 时 `filedup` 让文件结构体的生命周期独立于文件描述符；munmap 和 fork 复制时也需正确维护引用计数，防止 double-free 或 use-after-free。
4. **freewalk 契约**：`freewalk` 递归释放页表页，要求调用方必须先通过 `uvmunmap` 清除所有叶子映射。这是一个防御性设计 —— 如果调用方没清干净，panic 比静默泄漏内存更安全。
5. **mmap 写回的 POSIX 语义**：MAP_SHARED 写回只能修改文件已有范围内的数据，不能自动扩展文件。

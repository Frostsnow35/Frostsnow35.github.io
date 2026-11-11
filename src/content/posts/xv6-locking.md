---
title: "xv6-locking"
date: 2026-07-27T03:09:11.813649+00:00
category: "技术"
tags: ["xv6", "os"]
excerpt: "xv6-2025-fall 锁实验"
readTime: 29
legacyId: 13
---

在单核时代，操作系统是独裁的，代码按顺序执行。但多核 CPU 的出现打破了平静。并发成了常态，而**锁**就是我们在并发世界里的“交通灯”。本次实验通过两个极端场景，逼迫我们跳出教科书上简单的 `acquire/release`，直面真实多核环境下的两大性能瓶颈：锁争用与伪共享/缓存一致性。

## 第一部分：子实验一：Memory Allocator (Per-CPU Free Lists)

### 1. 实验任务分析

- **痛点现象**：运行 `kalloctest` 时，`kmem` 锁的 `#test-and-set` 数值极高（几万甚至十几万），说明多个 CPU 在疯狂自旋等待同一把锁。
- **根本原因**：原始 xv6 的物理内存分配器存在严重的可扩展性危机。它使用**单一全局空闲链表**，由**一把大锁** `kmem.lock` 保护。根据 Amdahl 定律，当三个进程在不同 CPU 上同时调用 `kalloc`/`kfree`（如 `kalloctest` 中的场景）时，内存分配成为了绝对的串行瓶颈。即使有 8 个核心，也只能排队一个一个分配，CPU 时间全浪费在执行 `amoswap` 指令的自旋死循环（`while(__sync_lock_test_and_set(...))`）中。
- **实验目标**：重构内存分配器，消除 `kmem` 锁的争用，使得 `kalloctest` 中 `kmem` 锁的 `#test-and-set` 降至 0 或极低值，同时保证 `usertests sbrkmuch` 依然能正确分配所有物理内存，不发生内存泄漏。

### 2. 相关源码深度剖析 (`kernel/kalloc.c`)

原始代码定义了一个全局结构体：

```c
struct {
  struct spinlock lock;
  struct run *freelist;
} kmem;
```

- **隐式链表的精妙**：`struct run` 只有一个指针成员 `next`。xv6 巧妙地利用了空闲页本身没有有用数据这一特点，直接将空闲物理页的前 8 个字节当作 `next` 指针使用，指向下一个空闲页。这是一种“零额外内存开销”的链表管理法。
- **单点瓶颈的根源**：在 `kfree` 中，拿到 `kmem.lock` 后执行 `r->next = kmem.freelist; kmem.freelist = r;`。在 `kalloc` 中，拿到锁后执行 `r = kmem.freelist; kmem.freelist = r->next;`。这里的“读-改-写”操作极度脆弱，必须由同一把全局锁严格串行化，这就导致了极高的锁争用。

### 3. 实验任务实现思路

- **核心哲学**：最好的锁，是没有锁。既然大家都要抢，那就“分家”——将全局单一资源划分为多个局部资源。
- **第一阶段：Per-CPU 拆分**。将单一的 `kmem` 改为大小为 `NCPU` 的数组 `kmem[NCPU]`。每个 CPU 拥有自己专属的空闲链表和专属锁。当 CPU 2 发生缺页中断需要分配内存时，它只拿 `kmem[2].lock`，与其他 CPU 完全并行，实现了真正的并行。
- **第二阶段：应对不均衡**。如果 CPU 0 的进程持续分配内存，而 CPU 1 闲置，CPU 0 的 `kmem[0].freelist` 很快就会枯竭。这就引出了 **Stealing（偷取）机制**。
- **Stealing 的边界条件**：当 `kalloc` 发现自己的链表为空时，它会遍历其他 CPU 的链表，拿别人的锁，从别人的链表头“偷”走一个页。关键点在于“偷多少”：我们只偷一个（取走头节点），而不是偷一半。因为如果偷太多，会导致被偷的 CPU 也立刻枯竭，引发“连锁 starvation（饿死）”波动。只偷一个，将偶尔的锁争用降到最低。
- **隐藏的致命陷阱**：获取当前 CPU ID (`cpuid()`) 依赖于读取 `tp` 寄存器（指向当前 CPU 的 `struct cpu` 结构体）。如果在读取 `tp` 时发生了时钟中断，调度器将进程迁移到了另一个 CPU，随后才关中断，那么 `kfree` 就会把内存错误地挂到新 CPU 的链表上。因此，必须先 `push_off()` 关中断，再调用 `cpuid()`。

### 4. 修改代码

#### 修改文件：`kernel/kalloc.c`

**修改点 1：重构数据结构**将原本的全局单结构体改为数组。

```c
// 原始代码：
// struct {
//   struct spinlock lock;
//   struct run *freelist;
// } kmem;

// 修改为：
struct {
  struct spinlock lock;
  struct run *freelist;
} kmem[NCPU];
```

**修改点 3：重构初始化函数** `kinit`初始化所有 CPU 的锁。此时系统刚启动，只有 CPU 0 在运行，所以 `freerange` 释放的所有内存都会自然地归入 `kmem[0]`。

```c
void
kinit()
{
  char lock_name[16]; // 用于动态生成锁的名字
  for(int i = 0; i < NCPU; i++) {
    snprintf(lock_name, sizeof(lock_name), "kmem_%d", i); // 生成如 "kmem_0"
    initlock(&kmem[i].lock, lock_name);
  }
  freerange(end, (void*)PHYSTOP);
}
```

**修改点 3：重构释放函数** `kfree`释放时，将内存归还给**当前运行 CPU** 的链表。注意中断保护。

```c
void
kfree(void *pa)
{
  struct run *r;
  if(((uint64)pa % PGSIZE) != 0 || (char*)pa < end || (uint64)pa >= PHYSTOP)
    panic("kfree");
  memset(pa, 1, PGSIZE);

  r = (struct run*)pa;

  push_off();  // 【关键】关中断，防止下面 cpuid() 时被调度到其他 CPU
  int id = cpuid(); 
  
  acquire(&kmem[id].lock);
  r->next = kmem[id].freelist;
  kmem[id].freelist = r;
  release(&kmem[id].lock);
  
  pop_off();   // 恢复中断状态
}
```

**修改点 4：重构分配函数** `kalloc`先查自己，自己没有再去“偷”别人的。

```c
void *
kalloc(void)
{
  struct run *r;

  push_off();
  int id = cpuid();

  // 第一步：从自己的 free list 分配（无争用快速路径）
  acquire(&kmem[id].lock);
  r = kmem[id].freelist;
  if(r)
    kmem[id].freelist = r->next;
  release(&kmem[id].lock);

  // 第二步：Stealing 机制（慢速路径，处理内存不均衡）
  if(!r) {
    for(int i = 0; i < NCPU; i++) {
      if(i == id) continue; // 跳过自己
      acquire(&kmem[i].lock);
      r = kmem[i].freelist;
      if(r) {
        kmem[i].freelist = r->next; // 偷走一个节点
        release(&kmem[i].lock);
        break; // 偷到就立刻退出循环
      }
      release(&kmem[i].lock);
    }
  }

  pop_off();

  if(r)
    memset((char*)r, 5, PGSIZE);
  return (void*)r;
}
```

---

## 第二部分：子实验二：Read-Write Lock (读写锁)

### 1. 实验任务分析

- **痛点现象**：`sys_uptime` 读取 `ticks`，`clockintr` 写入 `ticks++`。原始代码用普通自旋锁 `tickslock` 保护。这导致读-读之间也必须互斥，白白浪费了多核并行读取的能力。
- **实验目标**：实现读写锁 API。允许多个读者同时持有锁，写者独占锁。
- **硬性约束**：必须实现**写者优先**。一旦有写者在排队，后续的读者必须等待，绝对不能“偷跑”，否则写者会被源源不断的新读者饿死。

### 2. 相关源码深度剖析 (`kernel/spinlock.h` & `kernel/spinlock.c`)

- **xv6 自旋锁的底层硬件语义**：xv6 的 `acquire` 使用 RISC-V 的 `amoswap.w.aq` 指令，`release` 使用 `amoswap.w` 配合 `fence`。**锁不仅是互斥工具，它本质上是一个极重的“全屏内存屏障”**。`acquire` 会强迫当前 CPU 放弃本地缓存的旧数据（防读到旧值），`release` 会强迫当前 CPU 将临界区内的脏数据刷回主存（防数据丢失）。
- **API 的层次划分**：`spinlock.c` 提供了外层的 `read_acquire` 和包装函数，这些函数内部**已经帮我们调用了** `push_off()` **和** `pop_off()` 来关中断。我们只需要实现 `*_inner` 的核心逻辑，**在** `*_inner` **里绝不能再调用** `push_off()`，否则会引发嵌套计数器错误导致死锁。
- **结构体的暗示**：`spinlock.h` 中给出的桩结构体里包含 `struct spinlock lk;`，这不是多余的，而是为了让我们利用现有的、经过严格验证的内存屏障机制。

### 3. 实验任务实现思路

在经历了数十次死锁、偷跑、活锁的折磨后，我们沉淀出了最符合 RISC-V 底层硬件特性的**混合架构**：

- **为什么放弃纯无锁？** 我曾尝试完全不用内部锁 `lk`，纯靠 `__atomic_fetch_add` 和 `__atomic_load_n(..., __ATOMIC_ACQ_REL)` 实现。结果在 RISC-V 弱内存模型下惨败。因为如果读者读到的 `writer==0` 是“历史残留的旧 0”（而非写者释放时的新 0），C11 标准不保证它们之间建立同步关系，导致读者读到旧数据（稳定 `1/4` 失败）。
- **为什么引入内部自旋锁 (**`lk`**)？** 我们让 `lk` 专门负责保护元数据（`readers++`, `waiting_writers++`）的“读-改-写”不被撕裂，并**完美复用** `acquire/release` **自带的硬件级** `fence` **指令**，彻底解决跨缓存行的数据同步问题。
- **“门内”与“门外”的绝妙分工**：
  - **门内（持有** `lk` **时）**：做状态检查和修改。这里必须用 `__atomic_load_n(..., __ATOMIC_ACQUIRE)`。这不是为了硬件，而是为了**死死按住 GCC 编译器**，防止它把状态判断重排到拿锁之前。
  - **门外（释放** `lk` **后）**：进行忙等待。这里**必须**用 `__atomic_load_n(..., __ATOMIC_RELAXED)`。如果在这里用 `ACQUIRE` 或 `SEQ_CST`，会生成沉重的硬件 Fence 指令。在 QEMU 多核高并发下，密集的 Fence 会导致指令流水线拥堵，引发诡异的“活锁”（稳定卡死在 Step 6）。
- **写者优先的时序保证**：读者在增加 `readers` 之前，必须在内部锁的保护下双重检查 `waiting_writers`。只要看到排队牌，立刻释放内部锁退到门外，绝不能占坑。

### 4. 修改代码指引

#### 修改文件：`kernel/spinlock.h`

**修改点：完善读写锁数据结构**

```c
struct rwspinlock {
  struct spinlock lk;   // 【必须保留】内部自旋锁，用于保护下面三个变量的修改并提供硬件屏障
  int readers;          // 正在读的线程数
  int writer;           // 是否有写者正在写 (0或1)
  int waiting_writers;  // 正在等待写的写者数（用于实现写者优先）
};
```

#### 修改文件：`kernel/spinlock.c`

**修改点 1：实现初始化函数**

```c
void
initrwlock(struct rwspinlock *rwlk)
{
  initlock(&rwlk->lk, "rwlk"); // 初始化内部自旋锁
  rwlk->readers = 0;
  rwlk->writer = 0;
  rwlk->waiting_writers = 0;
}
```

**修改点 2：实现读锁获取**

```c
static void
read_acquire_inner(struct rwspinlock *rwlk)
{
  acquire(&rwlk->lk);
  // 门内用 ACQUIRE：约束编译器不重排，利用 acquire 建立同步关系
  while(__atomic_load_n(&rwlk->writer, __ATOMIC_ACQUIRE) || 
        __atomic_load_n(&rwlk->waiting_writers, __ATOMIC_ACQUIRE)) {
    release(&rwlk->lk);
    // 门外用 RELAXED：零开销自旋，极其关键！防止 QEMU 活锁
    while(__atomic_load_n(&rwlk->writer, __ATOMIC_RELAXED) || 
          __atomic_load_n(&rwlk->waiting_writers, __ATOMIC_RELAXED)) {
      ;
    }
    acquire(&rwlk->lk);
  }
  
  // 双重检查通过，安全占坑
  rwlk->readers++;
  release(&rwlk->lk);
}
```

**修改点 3：实现读锁释放**

```c
static void
read_release_inner(struct rwspinlock *rwlk)
{
  acquire(&rwlk->lk);
  rwlk->readers--;
  release(&rwlk->lk);
}
```

**修改点 4：实现写锁获取（排队与抢占）**

```c
static void
write_acquire_inner(struct rwspinlock *rwlk)
{
  acquire(&rwlk->lk); 
  rwlk->waiting_writers++; // 【关键】挂上排队牌，利用内部锁的 release 瞬间广播给所有读者
  
  // 等待里面的读者清空，或者前面的写者写完
  while(__atomic_load_n(&rwlk->readers, __ATOMIC_ACQUIRE) > 0 || 
        __atomic_load_n(&rwlk->writer, __ATOMIC_ACQUIRE)) {
    release(&rwlk->lk); 
    while(__atomic_load_n(&rwlk->readers, __ATOMIC_RELAXED) > 0 || 
          __atomic_load_n(&rwlk->writer, __ATOMIC_RELAXED)) {
      ;
    }
    acquire(&rwlk->lk); 
  }
  
  rwlk->writer = 1;       // 抢占写者状态
  rwlk->waiting_writers--; // 摘下排队牌
  release(&rwlk->lk); 
}
```

**修改点 5：实现写锁释放**

```c
static void
write_release_inner(struct rwspinlock *rwlk)
{
  acquire(&rwlk->lk);
  rwlk->writer = 0; // 释放写者状态，acquire/release 保证了前面的数据修改已经刷回主存
  release(&rwlk->lk);
}
```

---

## 第三部分：有价值的探讨与“坑”

在读写锁实验中，我们遇到了极其诡异的 `1/4 CPUs succeeded`（稳定读到旧数据）和 `Step 6 卡死`（活锁），这些失败背后的真相比代码本身更发人深省：

### 1. 纯无锁：RISC-V 弱内存模型特性所限制的

- **尝试**：一开始我们删掉了 `struct spinlock lk`，完全不用 `acquire/release`，纯靠 `__atomic_fetch_add` 和 `__atomic_load_n(..., __ATOMIC_ACQ_REL)` 实现读写锁。
- **现象**：逻辑上毫无破绽，但稳定有 CPU 读到旧数据，返回 `-1`。
- **深度思考**：在 x86 强内存模型下这可能没问题。但在 RISC-V 下，`ACQUIRE/RELEASE` 只对**特定同步变量**建立关系。如果读者通过无锁读到的 `writer==0` 是“历史残留的旧 0”，而不是写者释放时的“新 0”，那么它和写者之间**根本没有建立同步关系**，缓存行就不会失效，导致读到旧数据。**结论：不要在复杂状态机中轻易挑战弱内存模型的纯无锁编程。**

### 2. 屏障的滥用：`SEQ_CST` 导致的活锁

- **尝试**：为了解决上述读旧数据的问题，我们将所有 `__atomic_*` 升级为最重的 `__ATOMIC_SEQ_CST`（全局顺序一致性）。
- **现象**：单写者测试瞬间通过，但到了多写者高压测试直接卡死在 Step 6。
- **深度思考**：`SEQ_CST` 会在底层生成全屏的 `fence iorw, iorw`。在多个 CPU 极高频地抢占读写锁时，门外密集的 Fence 指令导致指令流水线严重拥堵，QEMU 的多核时间片轮转出现了微妙的“活锁”——大家都卡在 Fence 上，谁也抢不到内部锁。**结论：并发编程中，锁越重越好是错的，精确打击才是王道。**

### 3. 编译器的“降维打击”：指令重排

- **尝试**：在恢复使用内部自旋锁后，我们在门内写了普通的 `while(rwlk->writer || rwlk->waiting_writers)`。
- **现象**：依然报 `reader sneaked ahead`。
- **深度思考**：在 C 语言中，普通变量读取没有内存语义。GCC 编译器一看：“既然只是读一下判断，我完全可以把这两次读取指令，直接提前到你拿内部锁之前执行！” 结果 CPU 拿到锁后，用的是拿锁前读到的旧状态进行判断，导致逻辑失效。必须使用 `__atomic_load_n(..., __ATOMIC_ACQUIRE)` 才能死死按住编译器。

---

## 第四部分：总结

### 1. 性能优化的终极法则：数据划分

- **经验总结**：消除锁争用最有效的方法不是优化锁算法（如 MCS 锁），而是消除共享状态。将全局变量拆分为 Per-CPU 变量，是内核中极其强大的武器。
- **举一反三**：Linux 内核中的 `percpu` 计数器（如网络包丢包统计）、`Slab` 分配器中每个 CPU 的局部缓存，甚至是用户态高性能网络框架 `DPDK`，无一不在使用这种“先分后合/按需偷取”的架构模式。

### 2. 锁的本质：不仅是互斥，更是内存同步

- **经验总结**：初学者以为锁只是“不让别人进”。实际上，`acquire` 里的 `__sync_synchronize` 是在**清空本地缓存视角**（强制后续读操作去主存拉取）；`release` 里的屏障是在**强制把脏数据刷回主存**。锁是建立在硬件缓存一致性协议之上的同步原语。
- **举一反三**：在以后设计任何无锁数据结构（如 Ring Buffer）时，如果发现多核数据不一致，第一反应不应该是加锁，而应该是问自己：“我有没有正确地使用 `smp_mb()` 或 `ACQUIRE/RELEASE` 来建立生产者和消费者之间的同步关系？”

### 3. 读写锁的“写者优先”是系统稳定的刚需

- **经验总结**：如果只实现读-读共享，不实现写者优先，在写操作稍微频繁的场景下，新读者会源源不断地插队，写者会活活饿死，导致系统更新不可用。

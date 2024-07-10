# Pytorch 要点记录

## 种子设置
```python
def seed_everything(seed=1029):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    # cudnn 需要额外设置以下内容
    torch.backends.cudnn.deterministic = True
```

## 数据集Dataset
### 映射型（Map-style）数据集
对于可以一次性载入内存的数据集，可以用这个方式加载。首先
```python
from torch.utils.data import Dataset
```
然后需要根据自己的需要，编写自己的数据集类，继承自Dataset，在这个类中，需要实现三个方法：构造方法，索引方法还有获取长度的方法
```
class MyDataset(Dataset):
    def __init__(self, data_file):
        self.data = self.load_data(data_file)

    def __getitem__(self, index):
        return self.data[index]
    
    def __len__(self):
        return len(self.data)
```
> 这里的index一般是整数，否则需要自定义sampler

### 迭代型（Iterable-style）数据集
对于超大数据集，可以定义这种数据集
```python
from torch.utils.data import IterableDataset
```
需要自己实现构造方法和迭代方法
```python
class MyIterableDataset(IterableDataset):
    def __init__(self, data_path):
        super(MyinterableDataset).__init__()
        assert(end > start)
        # init
        self.data_path = data_path
        self.data_list = os.listdir(self.data_path)
        self.start = 0
        self.end = len(data_list)
    
    def __iter__(self): #生成器函数生成迭代器对象
        # return iter(list(...))
        for i in range(self.start, self.end):
            with open(Path(self.data_path).join(self.data_list[i]).expanduser().resolve(), 'rb') as f:
                ...
                data = process(f)
                ...
                yield data
```
### 多进程的坑worker_init_fn
如果dataloader访问迭代式数据集，那么不同worker都会全部过一遍整个数据集，造成重复访问，需要设置worker_init_fn来定义每一个进程的数据集拷贝
```python
    from torch.utils.data import get_worker_info
    import math

    def worker_info_fn(worker_if):
        worker_info = get_worker_info()
        dataset = worker_info.dataset # 获取这个进程的数据集拷贝
        overall_start = dataset.start
        overall_end = dataset.end
        per_worker = int(math.ceil((overall_end - overall_start) / float(worker_info.num_workers)))
        worker_id = worker_info.id
        # 修改数据集范围
        dataset.start = overall_start + worker_id * per_worker
        dataset.end = min(overall_end, dataset.start + per_worker)
```

## 数据加载器DataLoader
DataLoader按照如下方式构造
```python
data_loader = DataLoader(dataset, batch_size, shuffle, sampler, collate_fn)
```
其中，sampler用于自定义采样器，它是一个index上的迭代器。
### collate_fn函数
用于后处理已经成批的数据。它接受一个成批的原始数据，如果dataset索引出来是‘form’，那么输入就是`[form1, form2, form3, ...]`
默认的collate_fn行为是
- 添加一个新维度作为batch维
- 自动将Numpy数组和Python数值转换为Pytorch张量
- 保留原始数据结构（元组，列表，字典）
在NLP任务中，通常需要自定义collate_fn用于分词，拼接，padding等操作
```python
def collote_fn(batch_samples):
    batch_sentence_1, batch_sentence_2 = [], []
    batch_label = []
    for sample in batch_samples:
        batch_sentence_1.append(sample['sentence1'])
        batch_sentence_2.append(sample['sentence2'])
        batch_label.append(int(sample['label']))
    X = tokenizer(
        batch_sentence_1, 
        batch_sentence_2, 
        padding=True, 
        truncation=True, 
        return_tensors="pt"
    )
    y = torch.tensor(batch_label)
    return X, y
```

## 计算图和自动求导
Torch的计算图是动态的，可以根据需要随时添加和删除节点。其中，由用户创建的张量是叶子结点，`is_leaf = True`，算子操作是非叶子结点。动态图的意思是，每次前向计算都会重新构建计算图，并在反向传播之后释放掉。这样可以支持很多灵活的计算。

Torch的自动求导是根据计算图从根结点反向传播实现的。只有`requires_grad == True and is_leaf == True`的张量才会被计算并保存梯度。中间结果或者没有指定需要求导的张量不会储存导数。

### in-place 操作
[一个好文](https://blog.csdn.net/weixin_43424450/article/details/129243898)
对于`requires_grad == True`的叶子结点，创建之后不允许进行in-place操作（立马报错），其道理在于pytorch开发者不想为了这样的奇葩操作进行冗余设计，比如让所有的算子都要保存原始输入，等等。

对于非叶子结点，可以进行in-place操作，当时backward的时候会报错，这是通过校对张量的`_version`字段实现的。

### 源码分析
[一个好文](https://hurray0.com/menu/152/)

### 自定义autograd.function
[一个好文](https://zhuanlan.zhihu.com/p/344802526)



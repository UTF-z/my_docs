# Hugging Face 要点记录

## Tokenizer

### 基本使用

tokenizer可以直接完成包括分词、token2id、padding、构建attention mask、truncate等操作，还可以通过设置return_tensors来指定返回的数据类型，包括torch.Tensor、numpy.ndarray、tf.Tensor。


```python
sequences = [
    "I've been waiting for a HuggingFace course my whole life.", 
    "So have I!"
]
tokens = tokenizer(sequences:List[str], padding=True, truncation=True, return_tensors="pt")
print(tokens)
```
```
{'input_ids': tensor([
    [  101,  1045,  1005,  2310,  2042,  3403,  2005,  1037, 17662, 12172,
      2607,  2026,  2878,  2166,  1012,   102],
    [  101,  2061,  2031,  1045,   999,   102,     0,     0,     0,     0,
         0,     0,     0,     0,     0,     0]]), 
 'attention_mask': tensor([
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])}
```
tokenizer的返回结果是一个字典，包含input_ids和attention_mask两个key，分别对应token id和attention mask。

tokenizer还可以对句子对进行处理，前两个参数分别是第一个句子列表和第二个句子列表。tokenizer会自动用分隔符将两个句子拼接起来。
```python
from transformers import AutoTokenizer

checkpoint = "bert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(checkpoint)

sentence1_list = ["First sentence.", "This is the second sentence.", "Third one."]
sentence2_list = ["First sentence is short.", "The second sentence is very very very long.", "ok."]

tokens = tokenizer(
    sentence1_list,
    sentence2_list,
    padding=True,
    truncation=True,
    return_tensors="pt"
)
print(tokens)
print(tokens['input_ids'].shape)
```
```
{'input_ids': tensor([
        [ 101, 2034, 6251, 1012,  102, 2034, 6251, 2003, 2460, 1012,  102,    0,
            0,    0,    0,    0,    0,    0],
        [ 101, 2023, 2003, 1996, 2117, 6251, 1012,  102, 1996, 2117, 6251, 2003,
         2200, 2200, 2200, 2146, 1012,  102],
        [ 101, 2353, 2028, 1012,  102, 7929, 1012,  102,    0,    0,    0,    0,
            0,    0,    0,    0,    0,    0]]), 
 'token_type_ids': tensor([
        [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]), 
 'attention_mask': tensor([
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])
}
torch.Size([3, 18])
```
这里的输出多了一个token_type_ids，用于区分两个句子。

### 添加token
1. `add_tokens`，用于添加普通的新token到词表的末尾，返回值是添加的token数目，如果token已经在`tokenizer.vocab`里面，那么不会添加。还可以设置`special_tokens`参数，设置为True，那么会将该token指定为特殊token，不会对它进行normalize（比如不会被转换成小写）。
`num_added_toks = tokenizer.add_tokens(["new_token1", "my_new-token2"])`
2. `add_special_tokens`，用于添加特殊的token到词表的末尾，并且会注册tokenizer相关的attribute。参数形式是一个dict[str, str]，key是特殊token的名字，只能从“bos_token, eos_token, unk_token, sep_token, pad_token, cls_token, mask_token, additional_special_tokens”中选择。value是token的值。特殊token不会被normalize（比如不会被转换成小写）。 `add_tokens`和`add_special_tokens`的区别是，`add_tokens`不会注册tokenizer相关的attribute，而`add_special_tokens`会注册。

*添加了token之后需要调整embedding矩阵的大小，否则会报错。*
```python
model.resize_token_embeddings(len(tokenizer))
```
新的token embedding会加到embedding矩阵的末尾。

默认情况下，新添加的token embedding是随机初始化的，也可以手动初始化，比如
- 直接赋值
```python
tokenizer.add_tokens(["<my_new_token>"])
model.resize_token_embeddings(len(tokenizer))
with torch.no_grad():
    model.embeddings.word_embeddings.weight[-2:, :] = torch.zeros([2, model.config.hidden_size], require_grad=True)
```

- 初始化为已有token的embedding
```python
token_id = tokenizer.convert_tokens_to_ids('entity')
token_embedding = model.embeddings.word_embeddings.weight[token_id, :]
with torch.no_grad():
    for i in range(1, num_added_toks+1):
        model.embeddings.word_embeddings.weight[-i, :] = token_embedding.clone().detach().requires_grad_(True)
```

- 初始化为token语义
```python
new_token = ['[BOE]', '[EOE]']
description = ['beginning of entity', 'end of entity']
with torch.no_grad():
    for i, desc in enumerate(reversed(description), start = 1):
        desc_ids = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(desc))
        new_embedding = model.embeddings.word_embeddings.weight[desc_ids, :].mean(dim = 0)
        model.embeddings.word_embeddings.weight[-i] = new_embedding.clone().detach().requires_grad_(True)
```

    

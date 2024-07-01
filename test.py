import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModel

class Mydata(Dataset):

    def __init__(self, n):
        self.n = n
        return
    
    def __getitem__(self, idx):
        return {
            'idx': idx,
            'n': self.n
        }
    
    def __len__(self):
        return self.n
    
checkpoint = 'bert-base-uncased'
tokenizer = AutoTokenizer.from_pretrained(checkpoint)

tokenizer.add_special_tokens({'cls_token': '[MY_CLS]'})
tokenizer.add_tokens('[MY_CLS2]', special_tokens=True)

model = AutoModel.from_pretrained(checkpoint)

model.resize_token_embeddings(len(tokenizer))
print(type(model.embeddings.word_embeddings.weight))

model.embeddings.word_embeddings.weight[-2:, :] = torch.zeros([2, model.config.hidden_size], requires_grad=True)
import torch
import torch.nn as nn
import torch.nn.functional as F

# hyperparameters

batch_size=32
block_size=8
max_iters=5000
eval_interval=300
learning_rate=1e-3
device='cude' if torch.cuda.is_available() else 'cpu'
eval_iters=200
n_embd=32
head_size=16

torch.manual_seed(1337)

with open('input.txt','r',encoding='utf-8') as f:
    text=f.read()

chars=sorted(list(set(text)))
vocab_size=len(chars)

stoi={s:i for i,s in enumerate(chars)}
itos={i:s for s,i in stoi.items()}
encode=lambda s:[stoi[c] for c in s]
decode=lambda l:''.join([itos[i] for i in l])

data=torch.tensor(encode(text),dtype=torch.long)
n=int(0.9*len(data))
train_data=data[:n]
val_data=data[n:]

def get_batch(split):
    data=train_data if split=='train' else val_data
    ix=torch.randint(len(data)-block_size,(batch_size,))
    x=torch.stack([data[i:i+block_size] for i in ix])
    y=torch.stack([data[i+1:i+block_size+1] for i in ix])
    x,y=x.to(device),y.to(device)
    return x,y

@torch.no_grad()
def estimate_loss():
    out={}
    model.eval()
    for split in ['train','val']:
        losses=torch.zeros(eval_iters)
        for k in range(eval_iters):
            X,Y=get_batch(split)
            logits,loss=model(X,Y)
            losses[k]=loss.item()
        out[split]=losses.mean()
    model.train()
    return out

class Head(nn.Module):
    def __init__(self,head_size):
        super().__init__()
        self.query=nn.Linear(n_embd,head_size)
        self.key=nn.Linear(n_embd,head_size)
        self.value=nn.Linear(n_embd,head_size)
        self.register_buffer('tril',torch.tril(torch.ones(block_size,block_size)))
    
    def forward(self,x):
        B,T,C=x.shape
        k=self.key(x) #(B,T,C)
        q=self.query(x) #(B,T,C)

        wei=q@k.transpose(-2,-1)*head_size**-0.5 #(B,T,C) @(B,T,C) -> (B,T,T)
        wei=wei.masked_fill(self.tril[:T,:T]==0,float('-inf'))
        wei=F.softmax(wei,dim=-1)

        v=self.value(x)
        out=wei@v
        return out
    
class MultiHeadAttention(nn.Module):

    def __init__(self,num_heads,head_size):
        super().__init__()
        self.heads=nn.ModuleList([Head(head_size)for _ in range(num_heads)])
    
    def forward(self,x):
        return torch.cat([h(x) for h in self.heads],dim=-1)


class GPTLanguageModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table=nn.Embedding(vocab_size,n_embd)
        self.position_embedding_table=nn.Embedding(block_size,n_embd)
        self.sa_heads=MultiHeadAttention(4,n_embd//4)
        self.lm_head=nn.Linear(n_embd,vocab_size) 
    
    def forward(self,idx,targets=None):
        B,T=idx.shape

        tok_emb=self.token_embedding_table(idx) #(B,T,C)
        pos_emb=self.position_embedding_table(torch.arange(T,device=device))
        x=tok_emb+pos_emb
        x=self.sa_head(x)
        logits=self.lm_head(x) #(B,T,vocab_size)

        if targets is None:
            loss=None
        else:
            B,T,C=logits.shape
            logits=logits.view(B*T,C)
            targets=targets.view(B*T)
            loss=F.cross_entropy(logits,targets)
        return logits,loss
    
    def generate(self,idx,max_new_tokens):

        for _ in range(max_new_tokens):
            idx_cond=idx[:,-block_size:]
            logits,loss=self(idx_cond)
            logits=logits[:,-1,:]
            probs=F.softmax(logits,dim=-1)
            idx_next=torch.multinomial(probs,num_samples=1)
            idx=torch.cat((idx,idx_next),dim=1)
        return idx
    
model =GPTLanguageModel()
m=model.to(device)

optimizer=torch.optim.AdamW(model.parameters(),lr=learning_rate)

for iter in range(max_iters):

    if iter%eval_interval==0:
        losses=estimate_loss()
        print(f"step {iter}:train loss {losses['train']:.4f},val loss {losses['val']:.4f}")
    
    xb,yb=get_batch('train')

    logits,loss=model(xb,yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

context=torch.zeros((1,1),dtype=torch.long,device=device)
print(decode(m.generate(context,max_new_tokens=500)[0].tolist()))

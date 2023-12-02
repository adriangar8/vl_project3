import numpy as np
import random
from transformers import ResNetModel
from torch import nn
from torch.utils.data import Dataset
from PIL import Image
#from torchvision.transforms import v2
import torch
import pandas as pd
import evaluate
from torch.utils.data import DataLoader
import torch.optim as optim


import numpy as np
import random
from transformers import ResNetModel
from torch import nn
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from PIL import Image

# from torchvision.transforms import v2

from torchvision import transforms
import torch
import pandas as pd
import evaluate
import torch.utils.data
import matplotlib.pyplot as plt

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

print(DEVICE)

#base_path = 'C:/Users/Alex/Desktop/Universidad/Third Course/First Semester/Vision & Learning/PROJECT 3//'
img_path = '/fhome/gia01/vl_project3/data/Images/'
cap_path = '/fhome/gia01/vl_project3/data/captions.txt'

data = pd.read_csv(cap_path)
partitions = np.load('/fhome/gia01/vl_project3/baseline_model/flickr8k_partitions.npy', allow_pickle=True).item()

chars = ['<SOS>', '<EOS>', '<PAD>', ' ', '!', '"', '#', '&', "'", '(', ')', ',', '-', '.', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '=', '?', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

NUM_CHAR = len(chars)
idx2char = {k: v for k, v in enumerate(chars)}
char2idx = {v: k for k, v in enumerate(chars)}

TEXT_MAX_LEN = 201

class Data(Dataset):
    def __init__(self, data, partition):
        self.data = data
        self.partition = partition
        self.num_captions = 5
        self.max_len = TEXT_MAX_LEN
        self.img_proc = transforms.Compose([
            transforms.Resize((224, 224), antialias=True),
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
        ])
    def __len__(self):
        return len(self.partition)
    
    def __getitem__(self, idx):
        real_idx = self.num_captions*self.partition[idx]
        item = self.data.iloc[real_idx: real_idx+self.num_captions]
        ## image processing
        img_name = item.image.reset_index(drop=True)[0]
        img = Image.open(f'{img_path}{img_name}').convert('RGB')
        img = self.img_proc(img)
    
        ## caption processing
        caption = item.caption.reset_index(drop=True)[random.choice(list(range(self.num_captions)))]
        cap_list = list(caption)
        final_list = [chars[0]]
        final_list.extend(cap_list)
        final_list.extend([chars[1]])
        gap = self.max_len - len(final_list)
        final_list.extend([chars[2]]*gap)
        cap_idx = torch.Tensor([char2idx[i] for i in final_list])
        return img, cap_idx
    
class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.resnet = ResNetModel.from_pretrained('microsoft/resnet-18').to(DEVICE)
        self.gru = nn.GRU(512, 512, num_layers=1)
        self.proj = nn.Linear(512, NUM_CHAR)
        self.embed = nn.Embedding(NUM_CHAR, 512)

    def forward(self, img):
        batch_size = img.shape[0]
        feat = self.resnet(img)
        feat = feat.pooler_output.squeeze(-1).squeeze(-1).unsqueeze(0) # 1, batch, 512
        start = torch.tensor(char2idx['<SOS>']).to(DEVICE)
        start_embed = self.embed(start) # 512
        start_embeds = start_embed.repeat(batch_size, 1).unsqueeze(0) # 1, batch, 512
        inp = start_embeds
        hidden = feat
        for t in range(TEXT_MAX_LEN-1): # rm <SOS>
            out, hidden = self.gru(inp, hidden)
            inp = torch.cat((inp, out[-1:]), dim=0) # N, batch, 512
    
        res = inp.permute(1, 0, 2) # batch, seq, 512
        res = self.proj(res) # batch, seq, 80
        res = res.permute(0, 2, 1) # batch, 80, seq
        return res
    
bleu = evaluate.load('bleu')
meteor = evaluate.load('meteor')
rouge = evaluate.load('rouge')

def idx_to_sentence(indices, idx_to_word):
    return ' '.join(idx_to_word[idx] for idx in indices)


def train(EPOCHS):
    losses=[]
    metrics=[]
    data_train = Data(data, partitions['train'])
    data_valid = Data(data, partitions['valid'])
    data_test = Data(data, partitions['test'])

    dataloader_train = DataLoader(data_train, batch_size=4, shuffle=True)
    dataloader_valid = DataLoader(data_valid, batch_size=4, shuffle=True)
    dataloader_test = DataLoader(data_test, batch_size=4, shuffle=True)
    
    model = Model().to(DEVICE)
    model.train()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    crit = nn.CrossEntropyLoss()
    metric = "bleu"
    #metric = "bleu2"
    #metric = "rouge"
    #metric = "meteor"
    for epoch in range(EPOCHS):
        print("Entrando en la función")
        loss, res = train_one_epoch(model, optimizer, crit, metric, dataloader_train)
        print(f'train loss: {loss:.2f}, metric: {res:.2f}, epoch: {epoch}')
        losses.append(loss)
        metrics.append(res)
        #loss_v, res_v = eval_epoch(model, crit, metric, dataloader_valid)
        #print(f'valid loss: {loss_v:.2f}, metric: {res_v:.2f}')
    #loss_t, res_t = eval_epoch(model, crit, metric, dataloader_test)
    #print(f'test loss: {loss_t:.2f}, metric: {res_t:.2f}')
    
def train_one_epoch(model, optimizer, crit, metric, dataloader):
    total_loss= 0.0
    total_metric= 0.0

    for batch in dataloader:
        inputs, targets = batch
        inputs = inputs.to(DEVICE) 
        
        targets = targets.to(DEVICE)


        
        outputs= model(inputs)
        targets = targets.long()


        loss= crit(outputs,targets)

        total_loss += loss.item()


        

        # Take argmax to get most probable character indices
        outputs_idx = torch.argmax(outputs, dim=1) # el dim -1 es para decir que quieres encontrar el indice del valor máximo del tensor de probabilidades

        # Convert outputs and targets to sentences
        targets_sentence = ["".join(idx2char[idx.item()] for idx in target if idx.item() not in [char2idx['<EOS>'], char2idx['<PAD>'], char2idx['<SOS>']]) for target in targets]

        outputs_sentence = ["".join(idx2char[idx.item()] for idx in output if idx.item() not in [char2idx['<EOS>'], char2idx['<PAD>'], char2idx['<SOS>']]) for output in outputs_idx]

        
        #outputs_sentence = ''.join([idx2char[idx.item()] for idx in outputs if idx.item() not in [char2idx['<EOS>'], char2idx['<PAD>'], char2idx['<SOS>']]])
        #targets_sentence = ''.join([idx2char[idx.item()] for idx in targets if idx.item() not in [char2idx['<EOS>'], char2idx['<PAD>'], char2idx['<SOS>']]])


        
        METRIC = evaluate.load(str(metric).lower())


        if metric == "bleu":
                metriccompute = METRIC.compute(predictions=outputs_sentence, references=targets_sentence,max_order=1 )
        elif metric == "bleu2":
                metriccompute = METRIC.compute(predictions=outputs_sentence, references=targets_sentence,max_order=2 )
        else:
                metriccompute = METRIC.compute(predictions=outputs, references=targets )



        if metric == "rouge":
                total_metric += metriccompute['rougeL']
        else:
                total_metric += metriccompute[str(metric).lower()]
        

        
        
    avg_loss = total_loss / len(dataloader)
    avg_metric = total_metric / len(dataloader)
    print(f'train loss: {avg_loss:.2f}, metric: {avg_metric:.2f}')
    
    return avg_loss

def eval_epoch(model, crit, metric, dataloader):
    model.eval()
    total_loss = 0.0

    with torch.no_grad():
        for batch in dataloader:
            inputs, targets = batch
            inputs = inputs.to(DEVICE) 
            targets = targets.to(DEVICE)


            outputs = model(inputs)

            targets = targets.long()
            loss = crit(outputs, targets)

            total_loss += loss.item()


        
    avg_loss = total_loss / len(dataloader)

    print(f'valid loss: {avg_loss:.2f}')
    
    return avg_loss


EPOCHS= 50
train(EPOCHS)
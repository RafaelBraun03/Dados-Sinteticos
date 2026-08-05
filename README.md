# FastCamp Dados-Sinteticos
# Detecção e Contagem de Parafusos com Dataset 100% Sintético

Projeto final do curso de Dados Sintéticos — um pipeline completo que gera um dataset de imagens sintéticas no Blender, treina um detector de objetos (YOLOv8) exclusivamente com esses dados, e avalia o resultado tanto no domínio sintético quanto em fotos reais.

## Descrição do projeto

O projeto aborda, de forma simplificada, uma automação de controle de quantidade: detectar e contar individualmente três tipos de parafusos — **Phillips**, **Allen** e **Sextavado** — presentes em uma bandeja.

Em vez de coletar e anotar manualmente fotos reais desses parafusos (processo caro e demorado), todo o dataset de treinamento é gerado sinteticamente no Blender: as cenas são montadas e renderizadas por um script Python, que também calcula e salva as anotações (bounding boxes) automaticamente.

O modelo foi treinado **exclusivamente com dados sintéticos**. 

## Tecnologias utilizadas

| Categoria | Ferramenta |
|---|---|
| Modelagem e renderização 3D | Blender 5.2 LTS (motor Cycles) |
| Importação de modelos 3D | BlenderKit |
| Automação da cena e anotação | Python (API `bpy`, `bpy_extras`) |
| Treinamento do modelo | Ultralytics YOLOv8 (variante *nano*) |
| Ambiente de treino/avaliação | Jupyter Notebook |
| Validação de anotações e testes | OpenCV, Matplotlib |
| Deep learning (backend do YOLO) | PyTorch |

## Estrutura do repositório

```
.
├── Projeto Final/
│   ├── cena_projeto_final.blend        # cena configurada (bandeja, templates, luz, câmera)
│   └── gerador_dataset.py         # script único: spawn, luz, material, render, anotação YOLO
├── notebooks/
│   ├── validacao_anotacoes.ipynb  # desenha as bounding boxes salvas sobre a imagem, para conferência
│   └── treinamento_parafusos.ipynb # treino, avaliação e testes com imagens reais
├── dataset/
│   ├── data.yaml                  # manifesto de classes e caminhos, usado pelo YOLOv8
│   └── (ver seção "Dataset" abaixo sobre onde obter as imagens)
├── resultados/
│   ├── results.csv                # métricas por época geradas pelo treino
│   ├── confusion_matrix.png
│   ├── curvas_loss_mapa.png
│   └── deteccao_exemplo_*.png
└── README.md
```

## Dataset

- **700 imagens** renderizadas em **640×640 px**, split de **80% treino (560) / 20% validação (140)**
- De **0 a 4 parafusos de cada tipo** por imagem (quantidade sorteada independentemente por tipo), incluindo casos sem nenhum parafuso de um tipo
- Variações aplicadas a cada renderização:
  - Posição de cada parafuso dentro da bandeja, com checagem de distância mínima entre vizinhos
  - Pose de repouso (90% deitado, 10% em pé), com rotação livre no eixo Z
  - Potência (6–18 W) e temperatura de cor da luz
  - Material da bandeja, alternando entre acabamento metálico e plástico (cor, rugosidade e metalicidade)
- Câmera fixa, vista superior
- Anotações no **formato YOLO** (`classe x_center y_center largura altura`, normalizado), geradas por projeção geométrica 3D→2D dos vértices de cada parafuso (`bpy_extras.object_utils.world_to_camera_view`), sem uso de máscaras/compositing
- Classes: `0: Phillips`, `1: Allen`, `2: Sextavado`

> As 700 imagens não estão commitadas neste repositório por questão de tamanho.Estão disponíveis em (https://drive.google.com/drive/folders/1dOAEgKoDpFtb2piQbSRrJ9Cy-tGvBE4B?usp=drive_link). O script `gerador_dataset.py` também permite gerar o dataset do zero (ver instruções abaixo).

## Como configurar o ambiente

### 1. Blender (geração do dataset)

- Blender **5.2 LTS** ou superior
- Nenhuma dependência externa — o script usa apenas a API `bpy` embutida no Blender

### 2. Python (treinamento e avaliação)

Recomenda-se um ambiente virtual (Anaconda) dedicado:

```bash
conda create -n dados_sinteticos python=3.11
conda activate dados_sinteticos
pip install ultralytics opencv-python matplotlib jupyter requests
```

O Ultralytics já instala o PyTorch automaticamente. Se houver GPU com CUDA disponível, ela será usada automaticamente pelo treino; caso contrário, roda em CPU (como neste projeto).

## Como reproduzir

### Passo 1 — Gerar o dataset no Blender

1. Abra `Projeto Final/blender/cena_projeto_final.blend` no Blender 5.2 LTS
2. Vá na aba **Scripting**, mo blender
3. Abra `Projeto Final/blender/gerador_dataset.py`
4. Confira as constantes no topo do arquivo, especialmente `DATASET_ROOT` (pasta de saída) e `NUM_IMAGES` (quantidade de imagens a gerar)
5. Rode o script (**Alt+P** ou botão *Run Script*)

O script imprime o progresso no console (`[Imagem X de N]`, tempo estimado restante) e, ao final, cria automaticamente a estrutura:

```
DATASET_ROOT/
├── train/images  train/labels
└── valid/images  valid/labels
```

### Passo 2 — Validar as anotações (opcional, mas recomendado)

Abra `notebooks/validacao_anotacoes.ipynb` e rode a célula de conferência: ela lê uma imagem gerada e seu `.txt` correspondente, desenha as bounding boxes sobre a imagem e exibe o resultado — útil para confirmar visualmente que a anotação está alinhada ao parafuso antes de treinar.

### Passo 3 — Criar o manifesto do dataset

Dentro do mesmo notebook (ou de uma célula própria), gere o `data.yaml` apontando para as pastas do dataset:

```yaml
path: /caminho/para/dataset
train: train/images
val: valid/images

names:
  0: Phillips
  1: Allen
  2: Sextavado
```

### Passo 4 — Treinar o modelo

Abra `notebooks/treinamento_parafusos.ipynb` e execute as células em ordem:

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")  # pesos pré-treinados no COCO (transfer learning)

results = model.train(
    data="caminho/para/data.yaml",
    epochs=22,
    imgsz=640,
    batch=16,
    name="parafusos_yolov8",
)
```

Os pesos treinados ficam salvos em `runs/detect/parafusos_yolov8/weights/best.pt`.

### Passo 5 — Testar o modelo

O mesmo notebook inclui células para:
- Rodar inferência e contagem por classe em uma imagem do conjunto de validação (sintética)
- Rodar inferência em qualquer imagem real, local ou por URL, para avaliar o *domain gap*

```python
model_treinado = YOLO("runs/detect/parafusos_yolov8/weights/best.pt")
resultado = model_treinado.predict("caminho/ou/url/da/imagem.jpg", conf=0.25)
```

## Resultados

Modelo: **YOLOv8n**, 22 épocas, batch 16, imagem 640×640, otimizador automático (SGD/AdamW).

| Métrica | Valor (época 22) |
|---|---|
| Precisão | 99,6% |
| Recall | 98,7% |
| mAP50 | 99,1% |
| mAP50-95 | 80,0% |

O modelo atinge desempenho muito alto no conjunto de validação **sintético**, com boa separação entre as 3 classes (matriz de confusão concentrada na diagonal, sem trocas de classe) e curvas de perda em queda consistente, sem sinais de overfitting.

Em fotos **reais**, o desempenho cai — resultado esperado e discutido no relatório como o *domain gap*: o dataset sintético não reproduz totalmente efeitos como reflexos especulares em metal, sombras reais, marcas de uso e desgaste dos parafusos, e ângulos de câmera fora do padrão fixo usado no treino.

## Possíveis melhorias
Considerando que o foco do projeto era o treino exclusivamente com dados sintéticos.
Segue alguns possíveis ajustes para reduzir o domain gap:

- Aumentar o volume e a diversidade do dataset sintético (mais variação de câmera, fundos, oclusão, construção de cenários mais variados)
- Testar fine-tuning com um pequeno número de fotos reais anotadas manualmente, combinando sintético + real



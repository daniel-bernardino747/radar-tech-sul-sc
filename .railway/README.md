# Infraestrutura no Railway

O projeto do Railway (serviço, volume, réplicas, build e variáveis) está declarado em
[`railway.py`](./railway.py). O que sair do arquivo é removido no `apply`; o volume em
`/data` guarda o estado do Radar e não pode sair.

As variáveis aparecem como `preserve()`: o valor fica só no Railway, nunca no repositório.

## Comandos

```sh
pip install -r .railway/requirements.txt   # o CLI avalia o arquivo com python3
railway config plan    # mostra o que mudaria, sem mudar nada
railway config apply   # aplica (pede confirmação)
```

No Windows, `python3` costuma apontar para o atalho da Microsoft Store. Nesse caso, use um
ambiente com o `railway-sdk` instalado e um `python3.exe` no `PATH` (por exemplo, copiando o
`python.exe` do ambiente para `python3.exe`).

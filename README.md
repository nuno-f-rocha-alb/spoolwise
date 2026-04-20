# 3D Print Manager

App Flask + Bootstrap-Flask (Bootstrap 5) para gerir encomendas de impressão 3D com MariaDB.

## Funcionalidades
- Inventário global de filamentos (stock em g, **preço médio ponderado** atualizado a cada compra).
- Definições globais: preço da electricidade (€/kWh), potência da impressora (W) e % lucro por defeito.
- Encomendas com múltiplos filamentos (multi-color), cálculo automático de custo de filamento, custo de electricidade, preço de venda e lucro.
- Ao criar uma encomenda o peso dos filamentos é automaticamente descontado ao stock. Ao apagar a encomenda o stock é reposto.
- Snapshot do preço do filamento e das definições no momento da encomenda (para que preços passados não mudem se alterares as definições).

## Correr com Docker

```bash
docker compose up --build
```

App em http://localhost:5000
MariaDB em `localhost:3306` (user `printing`, pass `printing`, db `printing_app`).

## Correr sem Docker (só a app, apontando para a MariaDB do compose)

```bash
docker compose up -d db
python -m venv .venv && source .venv/bin/activate  # ou .venv\Scripts\activate no Windows
pip install -r requirements.txt
cp .env.example .env
python run.py
```

## Fluxo típico
1. **Definições** → configurar preço da electricidade, potência da impressora e % lucro default.
2. **Filamentos → + Novo filamento** → registar filamento (opcionalmente com stock inicial e preço).
3. **Filamentos → Comprar** → cada nova compra atualiza o preço médio ponderado:
   `novo_avg = (stock_atual_kg * avg_atual + compra_kg * preço_compra) / (stock_atual_kg + compra_kg)`
4. **+ Nova encomenda** → escolher filamentos (multi), peso, tempo e % lucro. O stock é descontado.

## Modelo de cálculo
- `custo_filamento = Σ (peso_g / 1000 × preço_médio_€/kg)`
- `custo_luz = potência_W / 1000 × horas × €/kWh`
- `custo_total = custo_filamento + custo_luz`
- `preço_venda = custo_total × (1 + lucro_% / 100)`

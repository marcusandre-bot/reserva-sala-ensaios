import os
import hashlib
import uuid
from datetime import date

import pandas as pd
import streamlit as st
import portalocker

st.title("Paróquia Santa Teresinha- Reserva da Sala de Ensaios")

ARQUIVO = "reservas.csv"
COLUNAS = ["id", "data", "turno", "grupo", "pin_hash"]


# -------------------------
# Funções auxiliares
# -------------------------
def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def carregar_reservas() -> pd.DataFrame:
    # Se não existir, cria vazio
    if not os.path.exists(ARQUIVO):
        df0 = pd.DataFrame(columns=COLUNAS)
        with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
            df0.to_csv(f, index=False)
        return df0

    # Lê com trava
    with portalocker.Lock(ARQUIVO, "r", timeout=5) as f:
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS)

    # Garante colunas (se você tiver CSV antigo sem id/pin_hash)
    for c in COLUNAS:
        if c not in df.columns:
            df[c] = ""

    df = df[COLUNAS]
    return df


def salvar_reservas(df: pd.DataFrame) -> None:
    with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
        df.to_csv(f, index=False)


def turnos_por_data(d: date):
    # 0=seg ... 6=dom
    if d.weekday() <= 4:
        return ["19h - 22h"]
    return ["08h - 12h", "14h - 18h", "19h - 22h"]


def admin_pin_ok(pin_digitado: str) -> bool:
    # Admin PIN vem do Secrets (não fica no código)
    admin_pin = st.secrets.get("ADMIN_PIN", "")
    return bool(admin_pin) and pin_digitado == admin_pin


# -------------------------
# Carrega dados
# -------------------------
df = carregar_reservas()

# -------------------------
# Reserva
# -------------------------
data = st.date_input("Escolha a data", date.today())
turnos = turnos_por_data(data)

reservas_dia = df[df["data"] == str(data)]
turnos_disponiveis = [t for t in turnos if t not in reservas_dia["turno"].values]

st.subheader("Fazer reserva")

if turnos_disponiveis:
    turno_escolhido = st.selectbox("Escolha o turno", turnos_disponiveis)
    nome_grupo = st.text_input("Nome do grupo")

    pin = st.text_input(
        "Crie um PIN (senha curta) para poder cancelar depois",
        type="password",
        help="Ex.: 4 a 8 dígitos. Guarde esse PIN: sem ele não dá para cancelar (exceto o administrador).",
    )

    if st.button("Reservar", type="primary"):
        if not nome_grupo.strip():
            st.error("Digite o nome do grupo.")
        elif not pin.strip():
            st.error("Crie um PIN para esta reserva.")
        else:
            # Recarrega na hora do clique (pega estado mais recente)
            df_atual = carregar_reservas()
            ja_existe = ((df_atual["data"] == str(data)) & (df_atual["turno"] == turno_escolhido)).any()

            if ja_existe:
                st.warning("Esse turno já foi reservado por outra pessoa. Atualize a página e escolha outro.")
            else:
                nova = pd.DataFrame([{
                    "id": str(uuid.uuid4())[:8],
                    "data": str(data),
                    "turno": turno_escolhido,
                    "grupo": nome_grupo.strip(),
                    "pin_hash": hash_pin(pin.strip()),
                }])

                df_novo = pd.concat([df_atual, nova], ignore_index=True)
                salvar_reservas(df_novo)

                st.success("Reserva realizada com sucesso! ✅")
                st.info("Guarde seu PIN: ele será necessário para cancelar.")
                st.rerun()
else:
    st.warning("Todos os turnos dessa data já estão reservados.")

# -------------------------
# Reservas futuras (visualização)
# -------------------------
st.subheader("Reservas futuras")

df_view = carregar_reservas().copy()
df_view["data_dt"] = pd.to_datetime(df_view["data"], errors="coerce")

reservas_futuras = df_view[df_view["data_dt"] >= pd.to_datetime(date.today())].copy()
reservas_futuras = reservas_futuras.sort_values(by=["data_dt", "turno"])

if reservas_futuras.empty:
    st.info("Ainda não há reservas futuras.")
else:
    st.dataframe(
        reservas_futuras[["data", "turno", "grupo", "id"]],
        use_container_width=True,
        hide_index=True
    )

# -------------------------
# Cancelamento
# -------------------------
st.subheader("Cancelar reserva")

df_cancel = carregar_reservas().copy()
df_cancel["data_dt"] = pd.to_datetime(df_cancel["data"], errors="coerce")
df_cancel = df_cancel[df_cancel["data_dt"] >= pd.to_datetime(date.today())].copy()
df_cancel = df_cancel.sort_values(by=["data_dt", "turno"])

if df_cancel.empty:
    st.info("Não há reservas futuras para cancelar.")
else:
    df_cancel["label"] = df_cancel.apply(
        lambda r: f'{r["data"]} | {r["turno"]} | {r["grupo"]} | id={r["id"]}',
        axis=1
    )
    escolha = st.selectbox("Selecione a reserva", df_cancel["label"].tolist())

    pin_cancel = st.text_input(
        "Digite o PIN para cancelar (PIN da reserva ou PIN do administrador)",
        type="password"
    )

    if st.button("Cancelar reserva selecionada"):
        if not pin_cancel.strip():
            st.error("Digite um PIN.")
        else:
            # Encontra id escolhido
            id_escolhido = escolha.split("id=")[-1].strip()

            df_atual = carregar_reservas()
            linha = df_atual[df_atual["id"] == id_escolhido]

            if linha.empty:
                st.warning("Essa reserva não foi encontrada (talvez alguém já cancelou). Atualize a página.")
            else:
                pin_ok = (hash_pin(pin_cancel.strip()) == linha.iloc[0]["pin_hash"])
                admin_ok = admin_pin_ok(pin_cancel.strip())

                if pin_ok or admin_ok:
                    df_novo = df_atual[df_atual["id"] != id_escolhido].copy()
                    salvar_reservas(df_novo)
                    st.success("Reserva cancelada ✅")
                    st.rerun()
                else:
                    st.error("PIN incorreto. Só cancela com o PIN da reserva ou com o PIN do administrador.")


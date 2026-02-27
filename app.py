import os
import hashlib
import uuid
import calendar
from datetime import date

import pandas as pd
import streamlit as st
import portalocker

import base64
import requests
# -------------------------
# Config / Estilo
# -------------------------
st.set_page_config(page_title="Reserva Sala de Ensaios", layout="centered")

st.markdown("""
<style>
/* Sobe um pouco o conteúdo sem sumir o cabeçalho */
.block-container {
    padding-top: 2.5rem;
    padding-bottom: 2rem;
}

/* Título (h2) mais enxuto */
h2 {
    margin-top: 0.3rem;
    margin-bottom: 0.3rem;
}

/* Botões um pouco menores (calendário fica mais discreto) */
.stButton > button {
    padding: 0.15rem 0.35rem;
    font-size: 0.85rem;
    line-height: 1.05rem;
}

/* Dá uma “respirada” entre os botões */
div[data-testid="column"] .stButton {
    margin: 0.15rem 0;
}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<div style='text-align:center; font-size:22px; font-weight:600; margin-bottom: 0.6rem;'>
Paróquia Santa Teresinha<br>
<span style='font-size:16px; font-weight:400;'>
Reserva da Sala de Ensaios - Versão 1.1
</span>
</div>
""", unsafe_allow_html=True)


ARQUIVO = "reservas.csv"
COLUNAS = ["id", "data", "turno", "grupo", "pin_hash"]

# -------------------------
# Persistência no GitHub (reservas.csv)
# -------------------------
def github_config_ok() -> bool:
    return all(k in st.secrets for k in ["GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "GITHUB_FILE"])

def _gh_headers():
    return {
        "Authorization": f"token {st.secrets['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }

def github_get_file():
    """Retorna (content_str, sha) do arquivo no GitHub. Se não existir, retorna ("", None)."""
    repo = st.secrets["GITHUB_REPO"]
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    path = st.secrets["GITHUB_FILE"]

    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    r = requests.get(url, headers=_gh_headers(), timeout=20)

    if r.status_code == 404:
        return "", None

    r.raise_for_status()
    data = r.json()
    content_b64 = data.get("content", "")
    sha = data.get("sha")
    content = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""
    return content, sha

def github_put_file(content_str: str, sha_atual: str | None):
    """Salva content_str no GitHub. Usa SHA para evitar sobrescrever mudanças de outra pessoa."""
    repo = st.secrets["GITHUB_REPO"]
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    path = st.secrets["GITHUB_FILE"]

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": "Atualiza reservas.csv",
        "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if sha_atual:
        payload["sha"] = sha_atual

    r = requests.put(url, headers=_gh_headers(), json=payload, timeout=20)

    # 409/422 geralmente = conflito (alguém gravou antes). Nesse caso, você recarrega e tenta de novo.
    if r.status_code in (409, 422):
        raise RuntimeError("CONFLITO_GITHUB")

    r.raise_for_status()

def carregar_reservas() -> pd.DataFrame:
    """Carrega do GitHub (Cloud) ou do arquivo local (PC)."""
    if github_config_ok():
        content, _sha = github_get_file()
        if not content.strip():
            return pd.DataFrame(columns=COLUNAS)

        from io import StringIO
        try:
            df = pd.read_csv(StringIO(content), dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS)

    else:
        # --- modo local (secrets não configurado) ---
        if not os.path.exists(ARQUIVO):
            df0 = pd.DataFrame(columns=COLUNAS)
            with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
                df0.to_csv(f, index=False)
            return df0

        with portalocker.Lock(ARQUIVO, "r", timeout=5) as f:
            try:
                df = pd.read_csv(f, dtype=str)
            except Exception:
                df = pd.DataFrame(columns=COLUNAS)

    # garante colunas
    for c in COLUNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUNAS]

def salvar_reservas(df: pd.DataFrame) -> None:
    """Salva no GitHub (Cloud) ou no arquivo local (PC)."""
    if github_config_ok():
        # tenta gravar com proteção de conflito
        content_atual, sha = github_get_file()
        csv_str = df.to_csv(index=False)

        try:
            github_put_file(csv_str, sha)
        except RuntimeError as e:
            if str(e) == "CONFLITO_GITHUB":
                # recarrega e tenta 1 vez de novo (resolve a maioria dos casos)
                _content2, sha2 = github_get_file()
                github_put_file(csv_str, sha2)
            else:
                raise
    else:
        with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
            df.to_csv(f, index=False)
# -------------------------
# Funções auxiliares
# -------------------------
def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


#def carregar_reservas() -> pd.DataFrame:
    #if not os.path.exists(ARQUIVO):
        #df0 = pd.DataFrame(columns=COLUNAS)
        #with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
            #df0.to_csv(f, index=False)
        #return df0

    #with portalocker.Lock(ARQUIVO, "r", timeout=5) as f:
        #try:
           # df = pd.read_csv(f, dtype=str)
       # except Exception:
        #    df = pd.DataFrame(columns=COLUNAS)

   # for c in COLUNAS:
     #   if c not in df.columns:
      #      df[c] = ""

   # return df[COLUNAS]


#def salvar_reservas(df: pd.DataFrame) -> None:
   # with portalocker.Lock(ARQUIVO, "w", timeout=5) as f:
   #     df.to_csv(f, index=False)


def turnos_por_data(d: date):
    # 0=seg ... 6=dom
    if d.weekday() <= 4:
        return ["19h - 22h"]
    return ["08h - 12h", "14h - 18h", "19h - 22h"]


def admin_pin_ok(pin_digitado: str) -> bool:
    admin_pin = st.secrets.get("ADMIN_PIN", "")
    return bool(admin_pin) and pin_digitado == admin_pin


def norm_data(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# -------------------------
# Estado: data selecionada
# -------------------------
hoje = date.today()
if "data_sel" not in st.session_state:
    st.session_state["data_sel"] = hoje


# -------------------------
# Abas (Opção A)
# -------------------------
# -------------------------
# Abas (Calendário / Reservar / Cancelar / Lista)
# -------------------------
tab_cal, tab_reservar, tab_cancelar, tab_lista = st.tabs(
    ["📅 Calendário", "✅ Reservar", "❌ Cancelar", "📋 Reservas realizadas"]
)

# =========================================================
# TAB 1 — CALENDÁRIO
# =========================================================
with tab_cal:
    df = carregar_reservas()

    col_cal, col_leg = st.columns([1.15, 1])

    with col_leg:
        st.markdown("**Legenda**")
        st.markdown("🟩 **Livre** (0 reservas)")
        st.markdown("🟨 **Parcial** (1–2 reservas)")
        st.markdown("🟥 **Lotado** (3/3 ou 1/1)")
        st.caption("Clique no dia para selecionar a data e depois vá para a aba de Reservar.")
        st.info(f"Data selecionada: **{st.session_state['data_sel'].strftime('%d/%m/%Y')}**")

    with col_cal:
        #st.markdown("#### Calendário do mês")

        colA, colB = st.columns([1, 2])
        with colA:
            ano = st.number_input(
                "Ano",
                min_value=2020,
                max_value=2100,
                value=st.session_state["data_sel"].year,
                step=1,
            )
        with colB:
            mes_nome = st.selectbox(
                "Mês",
                list(calendar.month_name)[1:],
                index=st.session_state["data_sel"].month - 1,
            )
        mes = list(calendar.month_name).index(mes_nome)

        cal = calendar.monthcalendar(int(ano), int(mes))

        df_cal = df.copy()
        if not df_cal.empty:
            df_cal["data"] = df_cal["data"].astype(str).str[:10]

        ocupados = {}
        totais = {}

        for semana in cal:
            for dia in semana:
                if dia == 0:
                    continue
                dt = date(int(ano), int(mes), int(dia))
                tot = len(turnos_por_data(dt))
                dt_str = norm_data(dt)
                occ = int((df_cal["data"] == dt_str).sum()) if tot > 0 else 0
                ocupados[dt] = occ
                totais[dt] = tot

        dias_sem = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        cols_head = st.columns(7)
        for i, dsem in enumerate(dias_sem):
            cols_head[i].markdown(f"**{dsem}**")

        for semana in cal:
            cols = st.columns(7)
            for i, dia in enumerate(semana):
                if dia == 0:
                    cols[i].write("")
                    continue

                dt = date(int(ano), int(mes), int(dia))
                occ = ocupados.get(dt, 0)
                tot = totais.get(dt, 0)

                if tot == 0:
                    emoji = "⬜"
                    status_txt = "—"
                else:
                    if occ == 0:
                        emoji = "🟩"
                    elif occ < tot:
                        emoji = "🟨"
                    else:
                        emoji = "🟥"
                    status_txt = f"{occ}/{tot}"

                label = f"{dia} {emoji}\n{status_txt}"
                key = f"dia_{ano}_{mes}_{dia}"

                if cols[i].button(label, key=key):
                    st.session_state["data_sel"] = dt
                    st.rerun()


# =========================================================
# TAB 2 — RESERVAR
# =========================================================
with tab_reservar:
    data = st.date_input("Escolha a data", st.session_state["data_sel"])
    st.session_state["data_sel"] = data

    df = carregar_reservas()

    st.subheader("Fazer reserva")

    turnos = turnos_por_data(data)
    reservas_dia = df[df["data"] == str(data)]
    turnos_disponiveis = [t for t in turnos if t not in reservas_dia["turno"].values]

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


# =========================================================
# TAB 3 — CANCELAR
# =========================================================
with tab_cancelar:
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


# =========================================================
# TAB 4 — LISTA
# =========================================================
with tab_lista:
    st.subheader("Reservas REALIZADAS")

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


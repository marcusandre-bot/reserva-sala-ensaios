import streamlit as st
import pandas as pd
from datetime import date
import os

st.title("Reserva da Sala de Ensaios")

ARQUIVO = "reservas.csv"

# Criar arquivo se não existir
if not os.path.exists(ARQUIVO):
    df_inicial = pd.DataFrame(columns=["data", "turno", "grupo"])
    df_inicial.to_csv(ARQUIVO, index=False)

# Carregar reservas
df = pd.read_csv(ARQUIVO)

data = st.date_input("Escolha a data", date.today())
dia_semana = data.weekday()

turnos = []

if dia_semana <= 4:
    turnos = ["19h - 22h"]
elif dia_semana == 5:
    turnos = ["08h - 12h", "14h - 18h", "19h - 22h"]
elif dia_semana == 6:
    turnos = ["08h - 12h", "14h - 18h", "19h - 22h"]

# Verificar reservas existentes para essa data
reservas_dia = df[df["data"] == str(data)]

turnos_disponiveis = []
for turno in turnos:
    if turno not in reservas_dia["turno"].values:
        turnos_disponiveis.append(turno)

if turnos_disponiveis:
    turno_escolhido = st.selectbox("Escolha o turno", turnos_disponiveis)
    nome_grupo = st.text_input("Nome do grupo")

    if st.button("Reservar"):
        nova_reserva = pd.DataFrame({
            "data": [str(data)],
            "turno": [turno_escolhido],
            "grupo": [nome_grupo]
        })

        df = pd.concat([df, nova_reserva], ignore_index=True)
        df.to_csv(ARQUIVO, index=False)

        st.success("Reserva realizada com sucesso!")
        st.rerun()

else:
    st.warning("Todos os turnos dessa data já estão reservados.")

st.subheader("Reservas futuras")

df["data"] = pd.to_datetime(df["data"])

reservas_futuras = df[df["data"] >= pd.to_datetime(date.today())]
reservas_futuras = reservas_futuras.sort_values(by=["data", "turno"])

st.dataframe(reservas_futuras)
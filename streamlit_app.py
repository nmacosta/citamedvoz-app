import streamlit as st

# Título de la aplicación
st.title("Formulario de Información Médica")

# Campos de texto con las etiquetas especificadas
literal = st.text_area("LITERAL")
motivo_consulta = st.text_area("MOTIVO_CONSULTA")
enfermedad_actual = st.text_area("ENFERMEDAD_ACTUAL")  # Usar st.text_area para campos más largos
antecedentes = st.text_area("ANTECEDENTES")
examen_fisico = st.text_area("EXAMEN_FISICO")
dias_reposo = st.text_area("DIAS_REPOSO")
signos_vitales = st.text_area("SIGNOS_VITALES")
examenes = st.text_area("EXAMENES")
diagnosticos = st.text_area("DIAGNOSTICOS")
medicamentos = st.text_area("MEDICAMENTOS")
plan_de_accion = st.text_area("PLAN_DE_ACCION")
comentarios_modelo = st.text_area("COMENTARIOS_MODELO")

# Estructura para recibir la información (un diccionario de Python)
informacion_medica = {
    "LITERAL": literal,
    "MOTIVO_CONSULTA": motivo_consulta,
    "ENFERMEDAD_ACTUAL": enfermedad_actual,
    "ANTECEDENTES": antecedentes,
    "EXAMEN_FISICO": examen_fisico,
    "DIAS_REPOSO": dias_reposo,
    "SIGNOS_VITALES": signos_vitales,
    "EXAMENES": examenes,
    "DIAGNOSTICOS": diagnosticos,
    "MEDICAMENTOS": medicamentos,
    "PLAN_DE_ACCION": plan_de_accion,
    "COMENTARIOS_MODELO": comentarios_modelo,
}

# Opcional: Mostrar la información recopilada al usuario
st.subheader("Información Recopilada:")
st.write(informacion_medica)


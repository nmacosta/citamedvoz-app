import streamlit as st
import json

# Título de la aplicación
st.title("Formulario de Información Médica")

# Área de texto para pegar la salida de Colab
colab_output = st.text_area("Pega aquí la salida del diccionario de Python desde Google Colab:")

if st.button("Cargar Información"):
    if colab_output:
        try:
            informacion_medica = json.loads(colab_output) # Usar json.loads si la salida de Colab es un JSON válido
            # O si la salida de Colab es un string de diccionario de Python, podrías usar:
            # informacion_medica = eval(colab_output)
            # ¡Advertencia! eval() puede ser inseguro si la entrada no es de confianza.

            # Llenar los campos del formulario con la información extraída
            st.subheader("Información Cargada:")
            literal = st.text_area("LITERAL", value=informacion_medica.get("LITERAL", ""))
            motivo_consulta = st.text_area("MOTIVO_CONSULTA", value=informacion_medica.get("MOTIVO_CONSULTA", ""))
            enfermedad_actual = st.text_area("ENFERMEDAD_ACTUAL", value=informacion_medica.get("ENFERMEDAD_ACTUAL", ""))
            antecedentes = st.text_area("ANTECEDENTES", value=informacion_medica.get("ANTECEDENTES", ""))
            examen_fisico = st.text_area("EXAMEN_FISICO", value=informacion_medica.get("EXAMEN_FISICO", ""))
            dias_reposo = st.text_area("DIAS_REPOSO", value=informacion_medica.get("DIAS_REPOSO", ""))
            signos_vitales = st.text_area("SIGNOS_VITALES", value=str(informacion_medica.get("SIGNOS_VITALES", ""))) # Asegúrate de manejar diccionarios anidados
            examenes = st.text_area("EXAMENES", value=str(informacion_medica.get("EXAMENES", ""))) # Las listas se mostrarán como strings
            diagnosticos = st.text_area("DIAGNOSTICOS", value=str(informacion_medica.get("DIAGNOSTICOS", "")))
            medicamentos = st.text_area("MEDICAMENTOS", value=str(informacion_medica.get("MEDICAMENTOS", "")))
            plan_de_accion = st.text_area("PLAN_DE_ACCION", value=informacion_medica.get("PLAN_DE_ACCION", ""))
            comentarios_modelo = st.text_area("COMENTARIOS_MODELO", value=informacion_medica.get("COMENTARIOS_MODELO", ""))

            # Opcional: Mostrar la información recopilada al usuario
            # st.subheader("Información Recopilada:")
            # st.write(informacion_medica)

        except json.JSONDecodeError:
            st.error("El texto pegado no parece ser un diccionario JSON válido.")
        except Exception as e:
            st.error(f"Ocurrió un error al cargar la información: {e}")
    else:
        st.warning("Por favor, pega la salida de Google Colab en el área de texto.")
import streamlit as st
import json
import re
import ast # Para evaluar de forma segura literales como listas/diccionarios

# --- Función para Parsear la Salida del LLM ---
def parse_llm_output_to_dict(raw_text):
    """
    Parsea el texto crudo con formato [CLAVE]: VALOR... del LLM
    a un diccionario Python, optimizado para el formato de ejemplo.
    """
    informacion_extraida = {}
    lines = raw_text.strip().split('\n')
    current_key = None
    current_value = ""
    print("--- Iniciando Parseo Línea por Línea ---") # Debug en consola

    for line in lines:
        line_stripped = line.strip()
        # Ignorar líneas completamente vacías entre bloques, pero permitir indentación
        if not line_stripped and current_key is None:
             continue
        # Permitir líneas vacías *dentro* de un valor multilínea
        if not line_stripped and current_key is not None:
            current_value += "\n" # Preservar el salto de línea
            continue

        # Busca una clave como [ALGOCLAVE]: al inicio de la línea
        match = re.match(r'^\[([^\]]+)\]:(.*)', line_stripped)

        if match:
            key = match.group(1).strip()
            # Valor inicial en la misma línea (puede estar vacío)
            value_part = match.group(2).strip()
            print(f"Línea con Clave: '{key}', Valor inicial: '{value_part}'") # Debug

            # Guardar clave anterior si existe
            if current_key:
                 informacion_extraida[current_key] = current_value.strip()
                 print(f"  Guardando Clave Anterior: '{current_key}' = '{current_value.strip()[:50]}...'") # Debug

            current_key = key
            current_value = value_part # Empezar con el valor de la misma línea
        elif current_key: # Si no es una línea de clave nueva y ya tenemos una clave activa
            # Añadir esta línea (con su indentación original) al valor actual
            # Añadir \n si current_value no está vacío (para separar líneas)
            separator = "\n" if current_value else ""
            current_value += separator + line # Usar línea original para preservar formato interno
            print(f"  Añadiendo a '{current_key}': '{line[:50]}...'") # Debug
        else:
             print(f"Línea Ignorada (antes de primera clave): '{line[:50]}...'") # Debug

    # Guardar la última clave-valor
    if current_key:
        informacion_extraida[current_key] = current_value.strip()
        print(f"Guardando Última Clave: '{current_key}' = '{current_value.strip()[:50]}...'") # Debug

    print("--- Parseo Inicial Completado ---") # Debug
    print(f"Diccionario Inicial: { {k: str(v)[:50]+'...' for k,v in informacion_extraida.items()} }") # Debug

    # --- Procesamiento Posterior para Tipos Específicos ---
    print("--- Iniciando Procesamiento Posterior ---") # Debug
    keys_to_process = list(informacion_extraida.keys())

    for key in keys_to_process:
        value = informacion_extraida[key]
        print(f"Procesando Key: '{key}'") # Debug

        # Intentar parsear Dicts/Lists usando ast.literal_eval
        # Incluir todas las claves que se esperan como listas/diccionarios
        if key in ['SIGNOS_VITALES', 'EXAMENES', 'DIAGNOSTICOS', 'MEDICAMENTOS', 'PLAN_DE_ACCION']:
            try:
                # ast.literal_eval es más seguro que eval y funciona con literales Python
                parsed_value = ast.literal_eval(value)

                # Validar tipo esperado
                if key == 'SIGNOS_VITALES' and isinstance(parsed_value, dict):
                    informacion_extraida[key] = parsed_value
                    print(f"  '{key}' parseado como Diccionario.") # Debug
                elif key in ['EXAMENES', 'DIAGNOSTICOS', 'MEDICAMENTOS', 'PLAN_DE_ACCION'] and isinstance(parsed_value, list):
                    # Asegurar que los elementos internos sean strings y limpiar espacios
                    informacion_extraida[key] = [str(item).strip() for item in parsed_value]
                    print(f"  '{key}' parseado como Lista.") # Debug
                else:
                    # Se parseó pero no es el tipo esperado (raro si el LLM es consistente)
                    print(f"  WARNING: '{key}' evaluado a {type(parsed_value)}, no el tipo esperado. Se mantiene como string.") # Debug
            except (ValueError, SyntaxError, TypeError) as e:
                # Si ast.literal_eval falla (ej. formato incorrecto del LLM)
                print(f"  INFO: No se pudo parsear '{key}' con ast.literal_eval: {e}. Se mantiene como string.") # Debug
                # Dejar el valor como string original
            except Exception as e:
                 print(f"  ERROR inesperado parseando '{key}': {e}. Se mantiene como string.") # Debug

        # Quitar comillas externas de los valores que quedaron como strings simples
        if isinstance(informacion_extraida[key], str):
             current_str_val = informacion_extraida[key]
             # Comprobar si empieza y termina con el mismo tipo de comilla
             if (current_str_val.startswith('"') and current_str_val.endswith('"')) or \
                (current_str_val.startswith("'") and current_str_val.endswith("'")):
                 informacion_extraida[key] = current_str_val[1:-1]
                 print(f"  Strip outer quotes from '{key}'.") # Debug

    print("--- Procesamiento Posterior Finalizado ---") # Debug
    print(f"Diccionario Final: { {k: str(v)[:50]+'...' for k,v in informacion_extraida.items()} }") # Debug
    return informacion_extraida

# --- Interfaz de Streamlit ---
st.set_page_config(layout="wide") # Usar más espacio horizontal
st.title("Visor de Información Médica Extraída")
st.caption(f"Hora actual: {st.session_state.get('current_time', 'No disponible')}") # Mostrar hora si se necesita

# Área de texto para pegar la salida del LLM
raw_llm_output = st.text_area("Pega aquí la SALIDA DE TEXTO COMPLETA del script de Google Colab:", height=300)

if st.button("Cargar y Procesar Información"):
    if raw_llm_output:
        try:
            # --- 1. Parsear el TEXTO CRUDO usando nuestra función ---
            st.info("Procesando texto de entrada...")
            informacion_medica = parse_llm_output_to_dict(raw_llm_output)
            st.success("Texto procesado exitosamente!")

            # Usar dos columnas para mejor distribución
            col1, col2 = st.columns(2)

            # --- COLUMNA IZQUIERDA ---
            with col1:
                st.subheader("Detalles del Paciente y Consulta")
                motivo_consulta = st.text_area("MOTIVO_CONSULTA", value=informacion_medica.get("MOTIVO_CONSULTA", ""), height=100)
                enfermedad_actual = st.text_area("ENFERMEDAD_ACTUAL", value=informacion_medica.get("ENFERMEDAD_ACTUAL", ""), height=150)
                antecedentes = st.text_area("ANTECEDENTES", value=informacion_medica.get("ANTECEDENTES", ""), height=150)
                examen_fisico = st.text_area("EXAMEN_FISICO", value=informacion_medica.get("EXAMEN_FISICO", ""), height=150)
                dias_reposo = st.text_input("DIAS_REPOSO", value=informacion_medica.get("DIAS_REPOSO", "NO_ENCONTRADO"))

                st.subheader("SIGNOS VITALES")
                signos_vitales_data = informacion_medica.get("SIGNOS_VITALES", {})
                if isinstance(signos_vitales_data, dict):
                    num_sv = len(signos_vitales_data)
                    cols_sv = st.columns(num_sv if num_sv > 0 else 1)
                    i = 0
                    # Mostrar siempre en un orden fijo si es posible
                    sv_order = ["TAS", "TAD", "FC", "Weight", "Size", "IMC"]
                    for key in sv_order:
                         if key in signos_vitales_data:
                            value = signos_vitales_data[key]
                            with cols_sv[i % num_sv if num_sv > 0 else 0]:
                                display_value = str(value) if str(value) != "NO_ENCONTRADO" else "---"
                                st.metric(label=key, value=display_value)
                            i += 1
                    # Mostrar claves extra si las hubiera
                    extra_keys = [k for k in signos_vitales_data if k not in sv_order]
                    for key in extra_keys:
                         value = signos_vitales_data[key]
                         with cols_sv[i % num_sv if num_sv > 0 else 0]:
                              display_value = str(value) if str(value) != "NO_ENCONTRADO" else "---"
                              st.metric(label=key, value=display_value)
                         i += 1

                elif isinstance(signos_vitales_data, str):
                     st.text_area("Signos Vitales (Texto)", value=signos_vitales_data, height=100, disabled=True)
                else:
                    st.warning("Formato inesperado para SIGNOS_VITALES.")
                    st.json(signos_vitales_data)

            # --- COLUMNA DERECHA ---
            with col2:
                st.subheader("Evaluación y Tratamiento")

                st.subheader("EXÁMENES")
                examenes_data = informacion_medica.get("EXAMENES", [])
                if isinstance(examenes_data, list):
                    if examenes_data:
                        for examen in examenes_data: st.markdown(f"- {examen}")
                    else: st.info("No se especificaron exámenes.")
                elif isinstance(examenes_data, str):
                     st.text_area("Exámenes (Texto)", value=examenes_data, height=100, disabled=True)
                else: st.warning("Formato inesperado para EXAMENES."); st.json(examenes_data)

                st.subheader("DIAGNÓSTICOS")
                diagnosticos_data = informacion_medica.get("DIAGNOSTICOS", [])
                if isinstance(diagnosticos_data, list):
                    if diagnosticos_data:
                        for diagnostico in diagnosticos_data: st.markdown(f"- {diagnostico}")
                    else: st.info("No se especificaron diagnósticos.")
                elif isinstance(diagnosticos_data, str):
                     st.text_area("Diagnósticos (Texto)", value=diagnosticos_data, height=100, disabled=True)
                else: st.warning("Formato inesperado para DIAGNOSTICOS."); st.json(diagnosticos_data)

                st.subheader("MEDICAMENTOS")
                medicamentos_data = informacion_medica.get("MEDICAMENTOS", [])
                if isinstance(medicamentos_data, list):
                    if medicamentos_data:
                        for i, med_entry in enumerate(medicamentos_data):
                            if isinstance(med_entry, str):
                                # Parsear Nombre, Presentación, Dosis del string interno
                                nombre = med_entry.split('[PRESENTACION]')[0].strip()
                                presentacion_match = re.search(r"\[PRESENTACION\]:\s*(.*?)(?=\s*\[DOSIS\]:|$)", med_entry, re.IGNORECASE | re.DOTALL)
                                dosis_match = re.search(r"\[DOSIS\]:\s*(.*)", med_entry, re.IGNORECASE | re.DOTALL)
                                presentacion = presentacion_match.group(1).strip() if presentacion_match and presentacion_match.group(1) else "No especificada"
                                dosis = dosis_match.group(1).strip() if dosis_match and dosis_match.group(1) else "No especificada"
                                expander_title = f"**{nombre}**" if nombre else f"Medicamento {i+1}"

                                with st.expander(expander_title):
                                    st.text_input("Presentación", value=presentacion, key=f"med_pres_{i}", disabled=True)
                                    st.text_area("Dosis", value=dosis, key=f"med_dosis_{i}", disabled=True)
                            else: st.markdown(f"- Entrada de medicamento inesperada: {str(med_entry)}")
                    else: st.info("No se especificaron medicamentos.")
                elif isinstance(medicamentos_data, str):
                     st.text_area("Medicamentos (Texto)", value=medicamentos_data, height=150, disabled=True)
                else: st.warning("Formato inesperado para MEDICAMENTOS."); st.json(medicamentos_data)

                st.subheader("PLAN DE ACCIÓN")
                plan_data = informacion_medica.get("PLAN_DE_ACCION", [])
                if isinstance(plan_data, list):
                    if plan_data:
                        for item in plan_data: st.markdown(f"- {item}")
                    else: st.info("No se especificó plan de acción.")
                elif isinstance(plan_data, str):
                     st.text_area("Plan de Acción (Texto)", value=plan_data, height=150, disabled=True)
                else: st.warning("Formato inesperado para PLAN_DE_ACCION."); st.json(plan_data)

                st.subheader("COMENTARIOS DEL MODELO")
                comentarios_modelo_val = informacion_medica.get("COMENTARIOS_MODELO", "")
                st.text_area("Comentarios", value=comentarios_modelo_val, height=100, label_visibility="collapsed")


            # --- SECCIÓN INFERIOR (TRANSCRIPCIÓN) ---
            st.divider()
            with st.expander("Ver Transcripción LITERAL Completa", expanded=False):
                 literal = st.text_area("LITERAL", value=informacion_medica.get("LITERAL", ""), height=400, label_visibility="collapsed")

            # --- DEBUG (Opcional) ---
            # st.divider()
            # with st.expander("Ver Diccionario Parseado (Debug)"):
            #    st.json(informacion_medica)

        except Exception as e:
            st.error(f"Ocurrió un error inesperado en la aplicación Streamlit: {e}")
            st.exception(e) # Muestra más detalles del error
    else:
        st.warning("Por favor, pega la salida de Google Colab en el área de texto.")

# Para inicializar la hora si se muestra en caption
if 'current_time' not in st.session_state:
     from datetime import datetime
     import pytz # Necesita instalarse: pip install pytz
     try:
        # Obtener hora de Venezuela
        tz = pytz.timezone('America/Caracas')
        st.session_state['current_time'] = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z%z')
     except Exception:
         st.session_state['current_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
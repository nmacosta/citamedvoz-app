import streamlit as st
import google.generativeai as genai
import json
import time
import pathlib
import io # Necesario para manejar el archivo en memoria
from datetime import datetime
import pytz # Necesario si quieres mantener la hora local
import tempfile 
import os 


# --- 0. Configuración Inicial y Constantes ---
st.set_page_config(layout="wide", page_title="citamedVOZ")
st.title("CITAMED - Procesador de Audio Médico con IA Generativa")

# Define el prompt directamente aquí (combinado de Colab)
# Parte 1: Instrucciones iniciales
prompt_part1 = """
Por favor, realiza las siguientes tareas con el audio proporcionado:
1.  **Transcribe** el contenido completo del audio. Mantén la transcripción lo más fiel posible al audio original, sin resumir. Puedes añadir mínimas palabras de conexión si mejora mucho la legibilidad, pero prioriza la fidelidad absoluta.
2.  **Clasifica** la información extraída de la transcripción en un formato JSON **válido**.
3.  **Utiliza exactamente la siguiente estructura JSON** como plantilla. Rellena los campos con la información correspondiente extraída del audio.

**Estructura JSON requerida (salida SÓLO JSON):**
"""
# Parte 2: La estructura JSON
json_structure_example = '''
```json
{
    "status": "OK",
    "message": "SUCCESS",
    "data": {
        "existing-mrs": {
            "Literal": "AQUI_VA_LA_TRANSCRIPCION_COMPLETA_Y_FIEL_DEL_AUDIO._Incluir_observaciones_adicionales_si_no_encajan_en_otros_campos.",
            "MotivoConsulta": "EXTRAER_EL_MOTIVO_PRINCIPAL_DE_LA_CONSULTA_O_LLAMADA",
            "EnfermedadActual": "EXTRAER_LA_DESCRIPCION_DE_LA_ENFERMEDAD_ACTUAL_O_SINTOMAS_PRINCIPALES",
            "Antecedentes": "EXTRAER_ANTECEDENTES_PERSONALES_PATOLOGICOS_Y_NO_PATOLOGICOS_DEL_PACIENTE",
            "ExamenFisico": "EXTRAER_HALLAZGOS_DETALLADOS_DEL_EXAMEN_FISICO_DESCRITO_EN_EL_AUDIO",
            "DiasReposo": "EXTRAER_SI_SE_INDICA_DIAS_DE_REPOSO_PARA_LA_CONSULTA",
            "SignosVitales": {
                "FC": "EXTRAER_FRECUENCIA_CARDIACA_(pulsaciones_por_minuto)",
                "IMC": "EXTRAER_INDICE_DE_MASA_CORPORAL_SI_SE_MENCIONA_EN_SU_DEFECTO_CALCULALO_POR_FAVOR",
                "Size": "EXTRAER_ESTATURA_DEL_PACIENTE_(en_metros)",
                "TAD": "EXTRAER_TENSION_ARTERIAL_DIASTOLICA_(mmHg)",
                "TAS": "EXTRAER_TENSION_ARTERIAL_SISTOLICA_(mmHg)",
                "PESO": "EXTRAER_PESO_DEL_PACIENTE_(en_kg)"
            },
            "Examenes": [
                // Añadir objetos aquí por cada examen mencionado
                // Ejemplo: { "Name": "NOMBRE_EXAMEN_O_ESTUDIO_SOLICITADO", "Resultado": "EXTRAE_CUANDO_EN_EL_AUDIO_LO_MUESTRA","UnidadMedida": "BUSCA_LA_UNIDAD_DEL_VALOR" }
            ],
            "Diagnosticos": [
                // Añadir objetos aquí por cada diagnóstico/patología mencionado que tiene el paciente, no excluir ninguno de estos
                // Ejemplo: { "ID": "CODIGO_CIE_10", "Nombre": "NOMBRE_DIAGNOSTICO_MENCIONADO_DEL_PACIENTE" }
            ],
            "Medicinas": [
                // Añadir objetos aquí por cada medicamento mencionado que se haya administrado al paciente
                // Ejemplo: { "Nombre": "NOMBRE_COMERCIAL", "Presentacion": "FORMA", "Dosis": "DOSIS_Y_FRECUENCIA" }
            ],
            "PlanDeAccion": [
                // EXTRAER_CUALQUIER_INSTRUCCION_QUE_EL_MEDICO_INCLUYA_O_COMENTARIOS_NO_CLASIFICABLES_EN_EL_RESTO_DE_CATEGORIA
                //Añadir objetos aqui, donde el texto sea una instruccion y
                //Ejemplo: { "NUMERO_CONSECUTIVO": "INSTRUCCION_OBTENIDA" }
            ],
            "ComentariosModelo": "INCLUIR_CUALQUIER_OBSERVACION_DE_PROBLEMAS_QUE_HAYAS_ENCONTRADO_EN_LA_TAREA"
        }
    }
}
'''
# Parte 3: Instrucciones finales
prompt_part3_final_instructions = """
Instrucciones IMPORTANTES para el formato de salida:
No incluyas texto explicativo, saludos, respeta las categorias y la forma en que se desglozan en el ejemplo.
Para Diagnosticos, es necesario que busque el CIED_10 al que corresponde e incluyas en el atributo ID
Presta atencion durante el audio el transcurao del audio se mencionan varios diagnosticos/patologias del paciente.
Si encuentras en el audio algun examen de laboratorio con el valor que le corresponde al resultado, busca el simbolo o la unidad de medida que corresponde
Si no se mencionan Examenes, Diagnosticoss o Medicinas, deja las listas correspondientes vacías: [].
El campo LITERAL es crucial: debe contener la transcripción LITERAL del audio.
El campo MOTIVO_CONSULTA es importante: debe contener las razones porque el paciente asiste a consulta, no excluyas el preambulo que incluye el medico a las razones.
Presta atención a los tipos de datos esperados (números para signos vitales, cadenas para descripciones, listas para exámenes/diagnósticos/medicamentos).
Si una pieza específica de información (ej. Signos Vitales - FC) no se menciona explícitamente en el audio, utiliza la cadena NO_ENCONTRADO
"""
# Combinar el prompt
prompt_text = prompt_part1 + json_structure_example + prompt_part3_final_instructions

# --- 1. Configuración de la API Key de Google ---
api_key_configured = False
google_api_key = None
try:
    # Intenta obtener la clave desde los secretos de Streamlit
    # Debes configurar un secreto llamado 'GOOGLE_API_KEY' en tu app de Streamlit Cloud
    google_api_key = st.secrets.get("GOOGLE_API_KEY")
    if google_api_key:
        genai.configure(api_key=google_api_key)
        api_key_configured = True
        st.info("API Key de Google configurada correctamente desde los secretos.")
    else:
        st.error("Error: No se encontró la 'GOOGLE_API_KEY' en los secretos de Streamlit.")
        st.markdown("""
            **ACCIÓN REQUERIDA:**
            1.  Ve a la configuración de tu aplicación en Streamlit Cloud.
            2.  En la sección 'Secrets', añade un nuevo secreto llamado `GOOGLE_API_KEY`.
            3.  Pega tu clave API de Google como valor.
            4.  Guarda y reinicia la aplicación si es necesario.
            """)
except Exception as e:
    st.error(f"Ocurrió un error al intentar configurar la API Key: {e}")
    st.markdown("Verifica que has configurado correctamente el secreto 'GOOGLE_API_KEY'.")

# --- 2. Subida del Archivo de Audio ---
st.divider()
st.subheader("1. Sube tu archivo de audio")
uploaded_file = st.file_uploader(
    "Selecciona un archivo de audio (.ogg):",
    type=['ogg'],
    accept_multiple_files=False,
    help="Sube el archivo de audio que deseas procesar."
)

# --- 3. Botón de Procesamiento y Lógica Principal ---
st.divider()
if st.button("2. Procesar Audio y Generar Información", disabled=not api_key_configured or not uploaded_file):

    if uploaded_file is not None and api_key_configured:
        st.info(f"Archivo '{uploaded_file.name}' cargado. Iniciando procesamiento...")

        audio_file_ref = None
        google_upload_successful = False
        generation_successful = False
        response = None
        parsed_json = None
        json_display_placeholder = st.empty()
        temp_file_path = None # Para guardar la ruta del archivo temporal

        try:
            # --- 3.1. Guardar archivo subido a un archivo temporal y subir a Google AI ---
            with st.spinner(f"Preparando y subiendo '{uploaded_file.name}' a Google AI..."):
                upload_start_time = time.time()
                try:
                    # Crear un archivo temporal con el mismo sufijo (extensión)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                        temp_file.write(uploaded_file.getvalue()) # Escribir los bytes al archivo temporal
                        temp_file_path = temp_file.name # Obtener la ruta del archivo temporal

                    st.write(f"Archivo temporal creado en: {temp_file_path}")

                    # Ahora subir usando la ruta (path)
                    audio_file_ref = genai.upload_file(
                        path=temp_file_path, # <--- Usar path
                        display_name=f"streamlit_{int(time.time())}_{uploaded_file.name}",
                        mime_type="audio/ogg" # Especificar mime type es bueno
                    )
                    st.write(f"Archivo enviado a Google AI. Nombre de referencia: {audio_file_ref.name}. Esperando procesamiento...")

                    # Esperar a que el archivo esté activo (lógica de Colab adaptada)
                    while audio_file_ref.state.name == "PROCESSING":
                        st.write(f"Estado actual: {audio_file_ref.state.name}. Esperando 5 segundos...")
                        time.sleep(5)
                        try:
                            audio_file_ref = genai.get_file(audio_file_ref.name) # Re-obtener estado
                        except Exception as get_file_e:
                            st.warning(f"Error obteniendo estado: {get_file_e}. Reintentando...")
                            time.sleep(5)
                            continue # Reintentar obtener estado

                        if time.time() - upload_start_time > 300: # Timeout 5 min
                            raise TimeoutError(f"Timeout: El archivo '{audio_file_ref.name}' sigue en estado {audio_file_ref.state.name} tras 5 minutos.")

                    # Verificar estado final
                    if audio_file_ref.state.name == "FAILED":
                        raise ValueError(f"Error: Subida/procesamiento de '{audio_file_ref.name}' falló en Google AI.")
                    elif audio_file_ref.state.name != "ACTIVE":
                        st.warning(f"Estado final inesperado: {audio_file_ref.state.name}. Intentando continuar...")
                        google_upload_successful = True # Intentar aunque no sea 'ACTIVE'
                    else:
                        st.write(f"Archivo '{audio_file_ref.name}' está ACTIVO.")
                        google_upload_successful = True

                except Exception as e:
                    st.error(f"Error durante la subida o procesamiento en Google AI: {e}")
                    # Salir del bloque try principal si la subida falla
                    raise e

            if not google_upload_successful:
                st.error("El archivo no pudo ser procesado por Google AI. No se puede continuar.")
            else:
                # --- 3.2. Preparar Modelo y Generar Contenido ---
                with st.spinner("Preparando modelo y generando contenido (puede tardar varios minutos)..."):
                    try:
                        #model_name = 'gemini-1.5-pro-latest' # Puedes elegir el modelo
                        model_name = 'gemini-2.5-pro-exp-03-25' # O usar flash que es más rápido y barato
                        model = genai.GenerativeModel(model_name)
                        st.write(f"Usando modelo: {model_name}")

                        generation_config = genai.GenerationConfig(
                            temperature=0.1,
                            # response_mime_type="application/json" # Descomentar si quieres forzar salida JSON (¡puede fallar si el modelo no cumple!)
                        )

                        model_start_time = time.time()
                        # Enviar prompt y referencia del archivo de audio
                        response = model.generate_content(
                            [prompt_text, audio_file_ref],
                            generation_config=generation_config,
                            request_options={'timeout': 600} # Timeout 10 min para la generación
                        )
                        model_end_time = time.time()
                        st.write(f"Respuesta recibida del modelo en {model_end_time - model_start_time:.2f} segundos.")
                        generation_successful = True

                    except genai.types.generation_types.BlockedPromptException as blocked_error:
                        st.error(f"Error: La solicitud fue bloqueada por políticas de seguridad.")
                        try:
                            feedback = getattr(blocked_error, 'response', {}).get('prompt_feedback', None)
                            if feedback:
                                st.warning(f"Razón del bloqueo: {feedback}")
                            elif response and hasattr(response, 'prompt_feedback'):
                                st.warning(f"Feedback del Prompt (puede indicar bloqueo): {response.prompt_feedback}")
                        except Exception:
                            st.warning("(No se pudo obtener feedback detallado del bloqueo)")
                        # No continuar si está bloqueado
                        generation_successful = False

                    except Exception as e:
                        st.error(f"Ocurrió un error durante la generación de contenido: {e}")
                        if hasattr(e, 'message'): st.error(f"Detalle: {e.message}")
                        try:
                           if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                              st.warning(f"Feedback del Prompt (puede indicar problemas): {response.prompt_feedback}")
                        except Exception: pass
                        generation_successful = False # Marcar como fallida


                # --- 3.3. Procesar Respuesta y Extraer JSON ---
                if generation_successful and response:
                    st.write("Procesando respuesta del modelo...")
                    try:
                        response_text = response.text
                        json_block = None

                        # Intenta extraer JSON delimitado por ```json ... ```
                        start_marker = "```json"
                        end_marker = "```"
                        start_index = response_text.find(start_marker)
                        if start_index != -1:
                            start_index += len(start_marker)
                            end_index = response_text.find(end_marker, start_index)
                            if end_index != -1:
                                json_block = response_text[start_index:end_index].strip()
                                st.write("JSON extraído usando delimitadores ```json.")

                        # Si no, busca el primer { y el último }
                        if json_block is None:
                            json_start_index = response_text.find('{')
                            json_end_index = response_text.rfind('}')
                            if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                                json_block = response_text[json_start_index : json_end_index + 1].strip()
                                st.write("JSON extraído buscando primer '{' y último '}'.")
                            else: # Último recurso
                                json_block = response_text.strip()
                                st.warning("No se detectó estructura JSON clara con ``` o {}. Usando respuesta completa como posible JSON.")

                        # Validar y parsear el JSON extraído
                        try:
                            parsed_json = json.loads(json_block)
                            st.success("JSON extraído y validado exitosamente.")
                            
                            # --- INICIO: NUEVA SECCIÓN PARA MOSTRAR JSON COMPLETO ---
                            st.divider() # Separador visual
                            st.subheader("JSON Completo Recibido del Modelo")
                            with st.expander("Ver/Ocultar JSON completo", expanded=False): # Ponerlo en un expander por defecto cerrado
                                st.json(parsed_json, expanded=True) # 'expanded=True' dentro del expander para el widget json en sí
                            st.divider() # Otro separador visual
                            # --- FIN: NUEVA SECCIÓN ---

                        except json.JSONDecodeError as json_error:
                            st.error(f"Error: El texto extraído NO es un JSON válido.")
                            st.error(f"Detalle: {json_error}")
                            st.text_area("Texto recibido del modelo (con error de JSON):", value=json_block, height=200)
                            parsed_json = None # Asegurar que no se intente mostrar

                    except AttributeError:
                        st.error("Error: La respuesta del modelo no tiene el atributo 'text'.")
                        st.write("Respuesta completa recibida:")
                        st.write(response)
                        parsed_json = None
                    except Exception as proc_err:
                        st.error(f"Error procesando la respuesta del modelo: {proc_err}")
                        parsed_json = None

                elif not generation_successful:
                    st.warning("La generación de contenido no fue exitosa o fue bloqueada.")
                else: # response is None
                     st.error("No se recibió respuesta del modelo.")


        except Exception as main_e:
            st.error(f"Error en el flujo principal de procesamiento: {main_e}")
            # Asegurarse de que parsed_json es None para no intentar mostrar nada
            parsed_json = None

        finally:
            # --- 3.4. Limpieza de Recursos (Archivo en Google AI) ---
            if audio_file_ref and hasattr(audio_file_ref, 'name'):
                try:
                    with st.spinner(f"Limpiando archivo '{audio_file_ref.name}' de Google AI..."):
                        genai.delete_file(audio_file_ref.name)
                        st.write(f"Archivo temporal '{audio_file_ref.name}' eliminado de Google AI.")
                except Exception as e_clean:
                    st.warning(f"Error al eliminar archivo '{audio_file_ref.name}' de Google AI: {e_clean}. Puede requerir limpieza manual.")
            elif google_upload_successful:
                st.warning("No se pudo intentar eliminar el archivo de Google AI (falta referencia válida).")

            # Limpieza del archivo local no es necesaria explícitamente con st.file_uploader

            st.info("Proceso completado (con posibles errores indicados arriba).")


        # --- 4. Mostrar Resultados (si el JSON fue parseado) ---
        st.divider()
        st.subheader("3. Resultados del Procesamiento")

        if parsed_json:
            try:
                # Validar estructura básica y extraer datos médicos
                if parsed_json.get("status") == "OK" and "data" in parsed_json and "existing-mrs" in parsed_json["data"]:
                    informacion_medica = parsed_json["data"]["existing-mrs"]
                    st.success("Mostrando información extraída:")

                    # --- INICIO: SECCIONES EXPANDIBLES (Copiado de tu script Streamlit) ---

                    # SECCION: Consulta (3 Columnas)
                    with st.expander("Detalles de la Consulta", expanded=True):
                        col_motivo, col_enf, col_ant = st.columns(3)
                        with col_motivo:
                            st.subheader("Motivo Consulta")
                            st.text_area("MotivoConsulta", value=informacion_medica.get("MotivoConsulta", ""), height=200, label_visibility="collapsed", disabled=True, key="motivo_c")
                        with col_enf:
                            st.subheader("Enfermedad Actual")
                            st.text_area("EnfermedadActual", value=informacion_medica.get("EnfermedadActual", ""), height=200, label_visibility="collapsed", disabled=True, key="enf_act")
                        with col_ant:
                            st.subheader("Antecedentes")
                            st.text_area("Antecedentes", value=informacion_medica.get("Antecedentes", ""), height=200, label_visibility="collapsed", disabled=True, key="antec")

                    # SECCION: Examen Físico
                    with st.expander("Examen Físico"):
                        st.text_area("ExamenFisico", value=informacion_medica.get("ExamenFisico", ""), height=150, label_visibility="collapsed", disabled=True, key="exam_fis")

                    # SECCION: Signos Vitales
                    with st.expander("Signos Vitales"):
                        signos_vitales_data = informacion_medica.get("SignosVitales", {})
                        if isinstance(signos_vitales_data, dict) and signos_vitales_data:
                            num_sv = len(signos_vitales_data)
                            cols_sv = st.columns(min(num_sv, 6)) # Max 6 columnas
                            i = 0
                            sv_order = ["TAS", "TAD", "FC", "PESO", "Size", "IMC"] # Orden preferido
                            displayed_keys = set()

                            for key in sv_order:
                                if key in signos_vitales_data:
                                    value = signos_vitales_data[key]
                                    with cols_sv[i % min(num_sv, 6)]:
                                        display_value = str(value) if str(value) != "NO_ENCONTRADO" and value is not None else "---"
                                        st.metric(label=key, value=display_value)
                                    displayed_keys.add(key)
                                    i += 1

                            # Mostrar claves restantes no incluidas en el orden preferido
                            extra_keys = [k for k in signos_vitales_data if k not in displayed_keys]
                            for key in extra_keys:
                                value = signos_vitales_data[key]
                                with cols_sv[i % min(num_sv, 6)]:
                                    display_value = str(value) if str(value) != "NO_ENCONTRADO" and value is not None else "---"
                                    st.metric(label=key, value=display_value)
                                i += 1
                        elif isinstance(signos_vitales_data, dict) and not signos_vitales_data:
                             st.info("No se encontraron datos de Signos Vitales.")
                        else:
                            st.warning("Formato inesperado para SignosVitales en el JSON.")
                            st.json(signos_vitales_data)

                    # SECCION: Exámenes
                    with st.expander("Exámenes Solicitados"):
                        examenes_data = informacion_medica.get("Examenes", [])
                        if isinstance(examenes_data, list):
                            if examenes_data:
                                for examen_dict in examenes_data:
                                    if isinstance(examen_dict, dict):
                                        name = examen_dict.get("Name", "Nombre no especificado")
                                        resultado = examen_dict.get("Resultado", "Resultado no especificado")
                                        unidad = examen_dict.get("UnidadMedida", "")
                                        display_text = f"- **{name}:** {resultado}"
                                        if unidad and unidad != "NO_ENCONTRADO":
                                            display_text += f" ({unidad})"
                                        st.markdown(display_text)
                                    else:
                                        st.warning(f"Elemento inesperado en Examenes: {examen_dict}")
                            else:
                                st.info("No se especificaron exámenes.")
                        else:
                            st.warning("Formato inesperado para Examenes en el JSON.")
                            st.json(examenes_data)

                    # SECCION: Diagnósticos
                    with st.expander("Diagnósticos"):
                        diagnosticos_data = informacion_medica.get("Diagnosticos", [])
                        if isinstance(diagnosticos_data, list):
                            if diagnosticos_data:
                                for diag_dict in diagnosticos_data:
                                    if isinstance(diag_dict, dict):
                                        # --- OBTENER AMBOS CAMPOS ---
                                        nombre_diag = diag_dict.get("Nombre", "Nombre no especificado")
                                        diag_id = diag_dict.get("ID", "") # Obtener el ID, default a vacío si no existe

                                        # --- CONSTRUIR EL TEXTO A MOSTRAR ---
                                        display_text = f"- **{nombre_diag}**" # Empezar con el nombre en negrita

                                        # Añadir el ID solo si existe, no está vacío y no es "NO_ENCONTRADO"
                                        if diag_id and diag_id.strip() and diag_id.upper() != "NO_ENCONTRADO":
                                            display_text += f" (ID: {diag_id})"

                                        # Mostrar el texto combinado
                                        st.markdown(display_text)
                                        # --- FIN DE LA CORRECCIÓN ---
                                    else:
                                        st.warning(f"Elemento inesperado en Diagnosticos: {diag_dict}")
                            else:
                                st.info("No se especificaron diagnósticos.")
                        else:
                            st.warning("Formato inesperado para Diagnosticos en el JSON.")
                            st.json(diagnosticos_data)

                    # SECCION: Medicamentos
                    with st.expander("Medicamentos Indicados"):
                        medicamentos_data = informacion_medica.get("Medicinas", [])
                        if isinstance(medicamentos_data, list):
                            if medicamentos_data:
                                for i, med_dict in enumerate(medicamentos_data):
                                    if isinstance(med_dict, dict):
                                        nombre = med_dict.get("Nombre", f"Medicamento {i+1}")
                                        presentacion = med_dict.get("Presentacion", "No especificada")
                                        dosis = med_dict.get("Dosis", "No especificada")

                                        med_title = f"**{nombre}** ({presentacion})"
                                        st.markdown(med_title)
                                        st.text_area(f"Dosis_{i}", value=dosis, key=f"med_dosis_{i}", height=80, label_visibility="collapsed", disabled=True)
                                        st.divider()
                                    else:
                                        st.warning(f"Elemento inesperado en Medicinas: {med_dict}")
                            else:
                                st.info("No se especificaron medicamentos.")
                        else:
                            st.warning("Formato inesperado para Medicinas en el JSON.")
                            st.json(medicamentos_data)

                    # SECCION: Plan de Acción (CORREGIDA - Lista Numerada)
                    with st.expander("Plan de Acción"):
                        plan_data = informacion_medica.get("PlanDeAccion", [])

                        if isinstance(plan_data, list):
                            if plan_data:
                                items_markdown = [] # Lista para guardar los strings formateados
                                valid_items_found = False
                                for item_dict in plan_data:
                                    if isinstance(item_dict, dict) and len(item_dict) == 1:
                                        # Extraer la clave (número) y el valor (instrucción)
                                        # Asumiendo que solo hay una clave-valor por diccionario
                                        try:
                                            numero_consecutivo = list(item_dict.keys())[0]
                                            instruccion = list(item_dict.values())[0]

                                            # Validar que la clave sea (o parezca) un número
                                            try:
                                                num_val = int(numero_consecutivo)
                                                # Formatear como ítem de lista numerada markdown
                                                # IMPORTANTE: Usar el número como prefijo seguido de un punto y espacio
                                                items_markdown.append(f"{num_val}. {instruccion}")
                                                valid_items_found = True
                                            except ValueError:
                                                # Si la clave no es un número, usar bullet point como fallback
                                                # y añadirlo directamente a la salida, no a la lista numerada
                                                st.warning(f"Ítem en PlanDeAccion con clave no numérica: '{numero_consecutivo}'. Mostrando como texto:")
                                                st.markdown(f"- {instruccion}")


                                        except IndexError:
                                            # Diccionario vacío, ignorar o marcar
                                            st.warning("Se encontró un diccionario vacío en PlanDeAccion.")
                                    else:
                                        # Manejar si un elemento no es el diccionario esperado
                                        st.warning(f"Elemento inesperado en PlanDeAccion (no es dict de 1 elemento): {item_dict}. Mostrando como texto:")
                                        # Intentar mostrar el valor si es un string simple
                                        if isinstance(item_dict, str):
                                            st.markdown(f"- {item_dict}")
                                        elif isinstance(item_dict, dict): # Si es dict pero > 1 elemento
                                            st.markdown(f"- {item_dict}") # Mostrar dict como texto

                                # Unir todos los ítems formateados numéricamente en una sola cadena de markdown
                                if valid_items_found:
                                    st.markdown("\n".join(items_markdown))
                                elif not plan_data: # Si la lista original estaba vacía
                                    st.info("No se especificó plan de acción en el JSON (lista vacía).")
                                else: # Si la lista tenía datos pero ninguno era válido para numerar
                                    st.info("No se encontraron instrucciones numeradas válidas en PlanDeAccion. Se mostraron advertencias arriba si hubo ítems con formato inesperado.")
                            else:
                                st.info("No se especificó plan de acción en el JSON (lista vacía).")
                        # Mantener el fallback por si el formato no es una lista
                        elif isinstance(plan_data, str) and plan_data:
                            st.markdown(f"Plan: {plan_data}") # Mostrar como texto simple si es string
                        else:
                            st.warning("Formato inesperado para PlanDeAccion o está vacío.")
                            # Opcional: mostrar el formato inesperado si no es lista ni string
                            if not isinstance(plan_data, (list, str)):
                                st.json(plan_data)


                    # SECCION: Días de Reposo
                    with st.expander("Indicación de Reposo"):
                        dias_reposo_val = informacion_medica.get("DiasReposo", "NO_ENCONTRADO")
                        if dias_reposo_val != "NO_ENCONTRADO":
                             if str(dias_reposo_val).isdigit():
                                st.metric("Días de Reposo Indicados", value=dias_reposo_val)
                             else:
                                st.write(f"Indicación: {dias_reposo_val}")
                        else:
                            st.info("No se especificó indicación de reposo.")

                    # SECCION: Comentarios y Literal (2 Columnas)
                    with st.expander("Comentarios del Modelo y Transcripción Completa", expanded=True):
                        col_comm, col_lit = st.columns(2)
                        with col_comm:
                            st.subheader("Comentarios del Modelo")
                            comentarios_modelo_val = informacion_medica.get("ComentariosModelo", "")
                            st.text_area("Comentarios", value=comentarios_modelo_val, height=300, label_visibility="collapsed", disabled=True, key="comm_mod")
                        with col_lit:
                            st.subheader("Transcripción Literal")
                            literal_val = informacion_medica.get("Literal", "")
                            st.text_area("Literal", value=literal_val, height=300, label_visibility="collapsed", disabled=True, key="lit_tx")

                    # --- FIN: SECCIONES EXPANDIBLES ---

                elif parsed_json and "message" in parsed_json:
                    st.error(f"Error en la respuesta JSON recibida del modelo: {parsed_json.get('message', 'Mensaje no encontrado')}")
                    st.json(parsed_json)
                else:
                    st.error("El JSON generado por el modelo no tiene la estructura esperada (status, data, existing-mrs).")
                    st.json(parsed_json if parsed_json else {"error": "No se pudo parsear JSON"})

            except Exception as display_e:
                st.error(f"Ocurrió un error al mostrar los datos del JSON: {display_e}")
                st.exception(display_e)
                st.write("JSON problemático:")
                st.json(parsed_json)

        elif generation_successful: # Si la generación fue OK pero el parseo JSON falló
             st.error("No se pudo mostrar la información porque el JSON generado por el modelo no es válido o no se pudo extraer.")
        else: # Si hubo error antes de obtener JSON
            st.warning("No hay información para mostrar debido a errores en pasos anteriores (subida, generación, etc.).")

    elif not uploaded_file:
        st.warning("Por favor, sube un archivo de audio primero.")
    elif not api_key_configured:
         st.error("La API Key no está configurada. No se puede procesar.")

# --- Sección Opcional: Hora Actual ---
st.divider()
try:
    # Intenta usar zona horaria específica, si no, usa UTC o local
    tz = pytz.timezone('America/Caracas') # Cambia a tu zona horaria si es necesario
    current_time_str = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z%z')
except Exception:
    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " (Local/UTC)"
st.caption(f"Hora actual: {current_time_str}")
import streamlit as st
import google.generativeai as genai
import json
import time
import pathlib # Aunque no se usa directamente, genai puede depender de él
import io # Necesario para manejar el archivo en memoria
from datetime import datetime
import pytz # Necesario para zona horaria específica
import tempfile
import os

# --- IMPORTACIONES PARA GOOGLE SHEETS ---
import gspread
from google.oauth2.service_account import Credentials
import gspread.exceptions # Para capturar errores específicos de API
# --------------------------------------------

# --- 0. Configuración Inicial y Constantes ---
st.set_page_config(layout="wide", page_title="citamedVOZ")
st.title("CITAMED - Procesador de Audio Médico con IA Generativa")

# --- Prompt para Gemini ---
prompt_part1 = """
Por favor, realiza las siguientes tareas con el audio proporcionado:
1.  **Transcribe** el contenido completo del audio. Mantén la transcripción lo más fiel posible al audio original, sin resumir. Puedes añadir mínimas palabras de conexión si mejora mucho la legibilidad, pero prioriza la fidelidad absoluta.
2.  **Clasifica** la información extraída de la transcripción en un formato JSON **válido**.
3.  **Utiliza exactamente la siguiente estructura JSON** como plantilla. Rellena los campos con la información correspondiente extraída del audio.

**Estructura JSON requerida (salida SÓLO JSON):**
"""
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
prompt_part3_final_instructions = """
Instrucciones IMPORTANTES para el formato de salida:
No incluyas texto explicativo, saludos, respeta las categorias y la forma en que se desglozan en el ejemplo.
Para Diagnosticos, es necesario que busque el CIED_10 al que corresponde e incluyas en el atributo ID
Presta atencion durante el audio el transcurao del audio se mencionan varios diagnosticos/patologias del paciente.
Si encuentras en el audio algun examen de laboratorio con el valor que le corresponde al resultado, busca el simbolo o la unidad de medida que corresponde
En los examenes es necesario identificar si son examenes ya con resultado por el paciente o si son examenes solictados
El campo LITERAL es crucial: debe contener la transcripción LITERAL del audio.
El campo MOTIVO_CONSULTA es importante: debe contener las razones porque el paciente asiste a consulta, no excluyas el preambulo que incluye el medico a las razones.
Presta atención a los tipos de datos esperados (números para signos vitales, cadenas para descripciones, listas para exámenes/diagnósticos/medicamentos).
Si una pieza específica de información (ej. Signos Vitales - FC) no se menciona explícitamente en el audio, utiliza la cadena NO_ENCONTRADO
Si no se mencionan Examenes, Diagnosticoss o Medicinas, deja las listas correspondientes vacías: [].
"""
prompt_text = prompt_part1 + json_structure_example + prompt_part3_final_instructions

# --- CONSTANTES PARA GOOGLE SHEETS ---
GSHEET_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file' # A veces necesario para algunas operaciones de gspread
]
# Asegúrate que este orden sea EXACTO al de tu hoja de log
EXPECTED_GSHEET_COLUMNS = [
    "Timestamp", "Filename", "Model", "Status", "Message", "MotivoConsulta",
    "EnfermedadActual", "Antecedentes", "ExamenFisico", "DiasReposo",
    "SignosVitales_Resumen", "Examenes_Resumen", "Diagnosticos_Resumen",
    "Medicinas_Resumen", # Mapeado desde la columna '850mg' original
    "PlanDeAccion_Resumen", "ComentariosModelo", "Literal",
    "JSON_Completo"
]
# -----------------------------------

# --- FUNCIONES PARA GOOGLE SHEETS ---
def connect_to_gsheet():
    """Carga credenciales de Sheets desde secretos y conecta con gspread."""
    try:
        # Lee las credenciales JSON del secreto
        creds_json_str = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        try:
            # Parsea el string JSON a un diccionario
            creds_dict = json.loads(creds_json_str)
        except json.JSONDecodeError as json_err:
             st.error(f"GSHEET Error: No se pudo decodificar el JSON de credenciales: {json_err}")
             # Opcional: Mostrar inicio del JSON problemático para depurar
             # st.text_area("GSHEET: Inicio del JSON problemático:", creds_json_str[:200] + "...", height=50)
             return None

        # Crea las credenciales y autoriza gspread
        creds = Credentials.from_service_account_info(creds_dict, scopes=GSHEET_SCOPES)
        gc = gspread.authorize(creds)
        # st.write("GSHEET: Conexión establecida.") # Mensaje de depuración opcional
        return gc

    except KeyError:
        # Error si falta el secreto de credenciales
        st.error("GSHEET Error: Falta el secreto 'GOOGLE_CREDENTIALS_JSON'.")
        return None
    except Exception as e:
        # Captura cualquier otro error durante la conexión/autorización
        st.error(f"GSHEET Error al conectar/autenticar: {e}")
        return None

def get_worksheet(gc):
    """Obtiene la hoja de cálculo de log usando la URL del secreto."""
    try:
        # Lee la URL completa de la hoja desde los secretos
        sheet_url = st.secrets["GOOGLE_SHEET_LOG_URL"]
        # st.write(f"GSHEET: Intentando abrir hoja por URL: '{sheet_url[:50]}...'") # Mensaje de depuración opcional

        # Abre la hoja de cálculo usando su URL
        spreadsheet = gc.open_by_url(sheet_url)
        # Asume que se usará la primera hoja (sheet1)
        worksheet = spreadsheet.sheet1
        # st.write("GSHEET: Hoja obtenida por URL.") # Mensaje de depuración opcional
        return worksheet

    except KeyError:
        # Error si falta el secreto de la URL
         st.error("GSHEET Error: Falta el secreto 'GOOGLE_SHEET_LOG_URL'.")
         return None
    except gspread.exceptions.APIError as api_err:
         # Error específico de la API de Google (permisos, etc.)
         st.error(f"GSHEET Error de API al abrir por URL: {api_err}")
         st.error("Verifica que la URL sea correcta y que la cuenta de servicio tenga permisos de EDITOR.")
         return None
    except gspread.exceptions.SpreadsheetNotFound:
         # Error si la URL es incorrecta o la hoja no existe/no es accesible
         st.error(f"GSHEET Error 'SpreadsheetNotFound' al usar la URL.")
         st.error("Verifica que la URL sea correcta y que la hoja exista y sea accesible.")
         return None
    except Exception as e:
        # Captura cualquier otro error inesperado
        st.error(f"GSHEET Error inesperado al abrir por URL: {e}")
        return None
# ----------------------------------


# --- 1. Verificación de Secretos Necesarios ---
st.divider()
st.subheader("Verificación de Claves API y Secretos")
api_key_configured = False
google_sheets_configured = False

# Verificar API Key de Gemini
try:
    google_api_key = st.secrets.get("GOOGLE_API_KEY")
    if google_api_key:
        genai.configure(api_key=google_api_key)
        api_key_configured = True
        st.success("✅ API Key de Google Gemini configurada.")
    else:
        st.error("❌ Falta el secreto 'GOOGLE_API_KEY'.")
except Exception as e:
    st.error(f"Error configurando API Key Gemini: {e}")

# Verificar Secretos de Google Sheets (Credenciales JSON y URL de la hoja)
try:
    required_sheets_secrets = ["GOOGLE_CREDENTIALS_JSON", "GOOGLE_SHEET_LOG_URL"]
    missing_secrets = [s for s in required_sheets_secrets if s not in st.secrets]

    if not missing_secrets:
         google_sheets_configured = True
         st.success("✅ Secretos para Google Sheets encontrados (JSON y URL).")
    else:
         st.error(f"❌ Faltan secretos para Google Sheets: {', '.join(missing_secrets)}.")
         st.markdown("""
            **ACCIÓN REQUERIDA (Google Sheets):**
            1.  Asegúrate de tener `GOOGLE_CREDENTIALS_JSON` con el JSON de la cuenta de servicio.
            2.  Asegúrate de tener `GOOGLE_SHEET_LOG_URL` con la URL completa de tu hoja de log.
            """)
except Exception as e:
     st.error(f"Error verificando secretos de Sheets: {e}")


# --- 2. Subida del Archivo de Audio ---
st.divider()
st.subheader("1. Sube tu archivo de audio")
uploaded_file = st.file_uploader(
    "Selecciona un archivo de audio (.ogg):",
    type=['ogg'],
    accept_multiple_files=False,
    help="Sube el archivo OGG que contiene la consulta médica."
)

# --- 2.5 Selección del Modelo de IA ---
st.divider()
st.subheader("1.5. Selecciona el Modelo de IA")
# Define los modelos disponibles
model_options = ['gemini-2.5-pro-exp-03-25', 'gemini-2.5-flash-preview-04-17','gemini-1.5-flash-latest', 'gemini-1.5-pro-latest']
selected_model_name = st.selectbox(
    "Elige el modelo de IA Generativa:",
    options=model_options,
    index=0, # Modelo por defecto
    help="Selecciona el modelo a usar para procesar el audio."
)
st.info(f"Modelo seleccionado: **{selected_model_name}**")


# --- 3. Botón de Procesamiento y Lógica Principal ---
st.divider()
# El botón se deshabilita si falta la API Key de Gemini o no se ha subido archivo
process_button_disabled = not api_key_configured or not uploaded_file
if st.button("2. Procesar Audio y Generar Información", disabled=process_button_disabled):

    # Solo procede si hay archivo y la API de Gemini está lista
    if uploaded_file is not None and api_key_configured:
        st.info(f"Archivo '{uploaded_file.name}' cargado. Usando modelo '{selected_model_name}'. Iniciando procesamiento...")

        # Variables para controlar el flujo y almacenar resultados/referencias
        audio_file_ref = None
        google_upload_successful = False
        generation_successful = False
        response = None
        parsed_json = None # Aquí se guardará el JSON parseado si tiene éxito
        temp_file_path = None # Ruta al archivo temporal local

        try:
            # --- 3.1. Subir archivo a Google AI ---
            with st.spinner(f"Subiendo '{uploaded_file.name}' a Google AI..."):
                upload_start_time = time.time()
                try:
                    # Guarda el archivo subido en un archivo temporal local
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                        temp_file.write(uploaded_file.getvalue())
                        temp_file_path = temp_file.name

                    # Sube el archivo temporal a Google AI File Service
                    audio_file_ref = genai.upload_file(
                        path=temp_file_path,
                        display_name=f"streamlit_{int(time.time())}_{uploaded_file.name}",
                        mime_type="audio/ogg" # Asegura el tipo MIME correcto
                    )
                    # st.write(f"Archivo enviado ({audio_file_ref.name}). Esperando procesamiento...") # Opcional

                    # Espera a que el archivo esté listo (ACTIVE) en Google AI
                    while audio_file_ref.state.name == "PROCESSING":
                        time.sleep(5) # Espera prudencial
                        try:
                            # Re-obtiene el estado del archivo
                            audio_file_ref = genai.get_file(audio_file_ref.name)
                        except Exception as get_file_e:
                            # Si hay error obteniendo estado, espera y reintenta
                            st.warning(f"Error obteniendo estado: {get_file_e}. Reintentando...")
                            time.sleep(5)
                            continue

                        # Timeout para evitar esperas infinitas
                        if time.time() - upload_start_time > 300: # 5 minutos
                            raise TimeoutError(f"Timeout: El archivo '{audio_file_ref.name}' sigue en estado PROCESSING.")

                    # Verifica el estado final de la subida/procesamiento en Google AI
                    if audio_file_ref.state.name == "FAILED":
                        raise ValueError(f"Error: Subida/procesamiento de '{audio_file_ref.name}' falló en Google AI.")

                    google_upload_successful = (audio_file_ref.state.name == "ACTIVE")
                    if not google_upload_successful:
                        st.warning(f"Estado final de subida inesperado: {audio_file_ref.state.name}. Se intentará continuar.")
                    else:
                         st.write(f"Archivo '{audio_file_ref.name}' está ACTIVO y listo para usar.")

                except Exception as e:
                    # Captura cualquier error durante la subida
                    st.error(f"Error durante la subida a Google AI: {e}")
                    raise e # Propaga el error para detener el flujo si es necesario
                finally:
                     # Asegura la eliminación del archivo temporal local
                     if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.remove(temp_file_path)
                            # st.write(f"Archivo temporal local '{temp_file_path}' eliminado.") # Opcional
                        except Exception as e_remove:
                            st.warning(f"No se pudo eliminar archivo temporal local {temp_file_path}: {e_remove}")

            # Si la subida falló, no continuar
            if not google_upload_successful:
                st.error("Fallo en la subida a Google AI. No se puede procesar.")
            else:
                # --- 3.2. Generar Contenido con el Modelo Gemini ---
                with st.spinner(f"Generando contenido con '{selected_model_name}' (esto puede tardar)..."):
                    try:
                        # Instancia el modelo seleccionado por el usuario
                        model = genai.GenerativeModel(selected_model_name)
                        # Configuración de generación (opcional, ajusta según necesidad)
                        generation_config = genai.GenerationConfig(temperature=0.1)
                        # Llamada a la API de Gemini
                        model_start_time = time.time()
                        response = model.generate_content(
                            [prompt_text, audio_file_ref], # Combina prompt e info del archivo
                            generation_config=generation_config,
                            request_options={'timeout': 600} # Timeout para la llamada a la API (10 min)
                        )
                        model_end_time = time.time()
                        st.write(f"Respuesta del modelo recibida en {model_end_time - model_start_time:.2f} segundos.")
                        generation_successful = True

                    except genai.types.generation_types.BlockedPromptException as blocked_error:
                        # Captura errores de bloqueo por políticas de seguridad
                        st.error(f"Error: La solicitud fue bloqueada por políticas de seguridad.")
                        # Intenta mostrar feedback si está disponible
                        try:
                            feedback = getattr(blocked_error, 'response', {}).get('prompt_feedback', None)
                            if feedback: st.warning(f"Razón del bloqueo: {feedback}")
                            elif response and hasattr(response, 'prompt_feedback'): st.warning(f"Feedback: {response.prompt_feedback}")
                        except Exception: pass
                        generation_successful = False

                    except Exception as e:
                        # Captura otros errores durante la generación
                        st.error(f"Ocurrió un error durante la generación de contenido: {e}")
                        if hasattr(e, 'message'): st.error(f"Detalle: {e.message}")
                        try: # Intenta mostrar feedback si hubo respuesta parcial
                           if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                              st.warning(f"Feedback del Prompt: {response.prompt_feedback}")
                        except Exception: pass
                        generation_successful = False # Marcar como fallida

                # --- 3.3. Procesar Respuesta, Extraer JSON y Registrar en Google Sheets ---
                if generation_successful and response:
                    st.write("Procesando respuesta del modelo...")
                    json_block = None # Texto que potencialmente es JSON
                    parsed_json = None # Diccionario Python si el parseo es exitoso

                    try:
                        # Intenta extraer el bloque JSON de la respuesta de texto
                        response_text = response.text
                        start_marker = "```json"
                        end_marker = "```"
                        start_index = response_text.find(start_marker)

                        if start_index != -1: # Si encuentra ```json
                            start_index += len(start_marker)
                            end_index = response_text.find(end_marker, start_index)
                            if end_index != -1:
                                json_block = response_text[start_index:end_index].strip()
                                # st.write("JSON extraído usando delimitadores ```json.") # Opcional
                        else: # Si no, busca primer { y último }
                            json_start_index = response_text.find('{')
                            json_end_index = response_text.rfind('}')
                            if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                                json_block = response_text[json_start_index : json_end_index + 1].strip()
                                # st.write("JSON extraído buscando primer '{' y último '}'.") # Opcional
                        # Si nada funcionó, usa el texto completo como último recurso
                        if not json_block:
                            json_block = response_text.strip()
                            st.warning("No se detectó estructura JSON clara. Usando respuesta completa.")

                        # Intenta parsear el bloque extraído como JSON
                        try:
                            parsed_json = json.loads(json_block)
                            st.success("JSON extraído y validado exitosamente.")

                            # --- INICIO: LÓGICA PARA REGISTRAR EN GOOGLE SHEETS ---
                            if google_sheets_configured: # Solo si los secretos de Sheets están presentes
                                st.write("Intentando registrar datos en Google Sheet...")
                                try:
                                    # 1. Preparar los datos para la fila de la hoja
                                    # Obtener timestamp en zona horaria deseada
                                    try:
                                        tz = pytz.timezone('America/Caracas')
                                        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
                                    except Exception: # Fallback a UTC si pytz falla
                                        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + " UTC"

                                    filename = uploaded_file.name if uploaded_file else "NO_FILENAME"
                                    model_name_log = selected_model_name

                                    # Extraer datos del JSON parseado (con valores por defecto seguros)
                                    json_status = parsed_json.get("status", "NO_STATUS")
                                    json_message = parsed_json.get("message", "NO_MESSAGE")
                                    # Acceder de forma segura a la data anidada
                                    data = parsed_json.get("data", {})
                                    existing_mrs = data.get("existing-mrs", {}) if isinstance(data, dict) else {}

                                    motivo_consulta = existing_mrs.get("MotivoConsulta", "")
                                    enf_actual = existing_mrs.get("EnfermedadActual", "")
                                    antecedentes = existing_mrs.get("Antecedentes", "")
                                    exam_fisico = existing_mrs.get("ExamenFisico", "")
                                    # Asegurar que días de reposo sea string para la hoja
                                    dias_reposo = str(existing_mrs.get("DiasReposo", ""))
                                    comentarios_modelo = existing_mrs.get("ComentariosModelo", "")
                                    literal = existing_mrs.get("Literal", "")
                                    # Convertir el JSON completo a string para guardarlo
                                    json_completo_str = json.dumps(parsed_json, ensure_ascii=False, indent=2)

                                    # Crear resúmenes para campos complejos (listas/dicts)
                                    sv_data = existing_mrs.get("SignosVitales", {})
                                    sv_resumen = "; ".join([f"{k}: {v}" for k, v in sv_data.items() if v not in [None, "NO_ENCONTRADO", ""]]) if isinstance(sv_data, dict) else ""

                                    ex_data = existing_mrs.get("Examenes", [])
                                    ex_resumen = "; ".join([f"{e.get('Name', '')}: {e.get('Resultado', '')}".strip(": ") for e in ex_data if isinstance(e, dict)]) if isinstance(ex_data, list) else ""

                                    dx_data = existing_mrs.get("Diagnosticos", [])
                                    dx_resumen = "; ".join([f"{d.get('Nombre', '')} ({d.get('ID', '')})".strip(" ()") for d in dx_data if isinstance(d, dict)]) if isinstance(dx_data, list) else ""

                                    med_data = existing_mrs.get("Medicinas", [])
                                    med_resumen = "; ".join([f"{m.get('Nombre', '')} {m.get('Presentacion', '')} {m.get('Dosis', '')}".strip() for m in med_data if isinstance(m, dict)]) if isinstance(med_data, list) else ""

                                    plan_data = existing_mrs.get("PlanDeAccion", [])
                                    # Extrae solo el valor (la instrucción) de cada dict en la lista
                                    plan_resumen = "; ".join([list(p.values())[0] for p in plan_data if isinstance(p, dict) and len(p)==1 and list(p.values())[0]]) if isinstance(plan_data, list) else ""


                                    # 2. Crear la lista de datos en el orden EXACTO de las columnas esperadas
                                    row_data = [
                                        timestamp, filename, model_name_log, json_status, json_message,
                                        motivo_consulta, enf_actual, antecedentes, exam_fisico, dias_reposo,
                                        sv_resumen, ex_resumen, dx_resumen,
                                        med_resumen, # Columna 14
                                        plan_resumen, comentarios_modelo, literal,
                                        json_completo_str
                                    ]

                                    # 3. Validar longitud y Escribir en la hoja
                                    if len(row_data) != len(EXPECTED_GSHEET_COLUMNS):
                                        # Error crítico si el número de columnas no coincide
                                        st.error(f"GSHEET Error: Discrepancia en número de columnas. Esperadas: {len(EXPECTED_GSHEET_COLUMNS)}, Generadas: {len(row_data)}. No se registrará.")
                                    else:
                                        # Conecta a Google Sheets
                                        gc = connect_to_gsheet()
                                        if gc:
                                            # Obtiene la hoja de trabajo usando la URL
                                            worksheet = get_worksheet(gc)
                                            if worksheet:
                                                # Añade la fila al final de la hoja
                                                with st.spinner("Escribiendo registro en Google Sheet..."):
                                                    worksheet.append_row(row_data, value_input_option='USER_ENTERED')
                                                st.success("✅ ¡Registro agregado exitosamente a Google Sheet!")
                                            else:
                                                st.warning("GSHEET: No se pudo obtener la hoja de trabajo (verifica URL/Permisos). No se registró.")
                                        else:
                                             st.warning("GSHEET: No se pudo conectar con Google Sheets. No se registró.")

                                except Exception as log_err:
                                    # Captura errores durante el proceso de registro
                                    st.error(f"GSHEET Error durante el proceso de registro: {log_err}")
                                    st.exception(log_err) # Muestra traceback para depuración

                            else: # Si google_sheets_configured es False
                                st.warning("Registro en Google Sheet omitido porque faltan los secretos necesarios (JSON de credenciales o URL de la hoja).")
                            # --- FIN: LÓGICA PARA GOOGLE SHEETS ---

                            # Mostrar el JSON completo parseado en un expander
                            st.divider()
                            st.subheader("JSON Completo Recibido del Modelo")
                            with st.expander("Ver/Ocultar JSON completo", expanded=False):
                                st.json(parsed_json, expanded=True)
                            st.divider()

                        except json.JSONDecodeError as json_error:
                            # Error si el texto extraído no se pudo parsear como JSON
                            st.error(f"Error: El texto extraído del modelo NO es un JSON válido.")
                            st.error(f"Detalle del error: {json_error}")
                            # Muestra el texto problemático para ayudar a identificar el error
                            st.text_area("Texto recibido del modelo (con error de JSON):", value=json_block if json_block else response_text, height=200)
                            parsed_json = None # Asegurar que parsed_json es None si falla

                    except AttributeError:
                         # Error si la respuesta del modelo no tiene el atributo .text
                         st.error("Error: La respuesta del modelo no tiene el atributo 'text'.")
                         st.write("Respuesta completa recibida:")
                         st.write(response)
                         parsed_json = None # Marcar como fallido
                    except Exception as proc_err:
                        # Captura otros errores durante el procesamiento de la respuesta
                        st.error(f"Error procesando la respuesta del modelo: {proc_err}")
                        parsed_json = None # Marcar como fallido

                elif not generation_successful:
                    # Mensaje si la generación falló o fue bloqueada
                    st.warning("La generación de contenido no fue exitosa o fue bloqueada. No hay JSON para procesar.")
                else: # response is None
                    # Mensaje si no se recibió respuesta alguna
                     st.error("No se recibió respuesta del modelo.")

        # --- Manejo de Errores Generales del Flujo ---
        except Exception as main_e:
            st.error(f"Ocurrió un error en el flujo principal de procesamiento: {main_e}")
            st.exception(main_e) # Muestra el traceback completo para depuración
            parsed_json = None # Asegurar que es None si hay error antes de mostrar resultados

        finally:
            # --- 3.4. Limpieza de Recursos (Archivo en Google AI) ---
            # Intenta eliminar el archivo subido a Google AI para no acumular archivos
            if audio_file_ref and hasattr(audio_file_ref, 'name'):
                try:
                    # No usar spinner aquí para no ocultar mensajes finales
                    genai.delete_file(audio_file_ref.name)
                    st.caption(f"Archivo temporal '{audio_file_ref.name}' eliminado de Google AI.")
                except Exception as e_clean:
                    st.caption(f"Advertencia: No se pudo eliminar archivo '{audio_file_ref.name}' de Google AI: {e_clean}. Puede requerir limpieza manual.")
            elif google_upload_successful:
                 # Mensaje si la subida tuvo éxito pero no hay referencia para borrar
                 st.caption("No se pudo intentar eliminar el archivo de Google AI (falta referencia válida).")

            st.info("Proceso de análisis completado (revisa mensajes anteriores para posibles errores o advertencias).")


        # --- 4. Mostrar Resultados del Procesamiento ---
        st.divider()
        st.subheader("3. Resultados del Procesamiento")

        # Solo muestra resultados si el JSON fue parseado exitosamente (parsed_json no es None)
        if parsed_json:
            try:
                # Verifica la estructura básica esperada del JSON
                if parsed_json.get("status") == "OK" and "data" in parsed_json and isinstance(parsed_json.get("data"), dict) and "existing-mrs" in parsed_json["data"]:
                    informacion_medica = parsed_json["data"]["existing-mrs"]
                    st.success("Mostrando información médica extraída del audio:")

                    # --- SECCIONES DE VISUALIZACIÓN (SIN CAMBIOS RESPECTO A TU CÓDIGO ORIGINAL) ---

                    # SECCION: Consulta (3 Columnas)
                    with st.expander("Detalles de la Consulta", expanded=True):
                        col_motivo, col_enf, col_ant = st.columns(3)
                        with col_motivo:
                            st.subheader("Motivo Consulta")
                            st.text_area("MotivoConsulta_disp", value=informacion_medica.get("MotivoConsulta", "No encontrado"), height=200, label_visibility="collapsed", disabled=True, key="motivo_c_disp")
                        with col_enf:
                            st.subheader("Enfermedad Actual")
                            st.text_area("EnfermedadActual_disp", value=informacion_medica.get("EnfermedadActual", "No encontrado"), height=200, label_visibility="collapsed", disabled=True, key="enf_act_disp")
                        with col_ant:
                            st.subheader("Antecedentes")
                            st.text_area("Antecedentes_disp", value=informacion_medica.get("Antecedentes", "No encontrado"), height=200, label_visibility="collapsed", disabled=True, key="antec_disp")

                    # SECCION: Examen Físico
                    with st.expander("Examen Físico"):
                        st.text_area("ExamenFisico_disp", value=informacion_medica.get("ExamenFisico", "No encontrado"), height=150, label_visibility="collapsed", disabled=True, key="exam_fis_disp")

                    # SECCION: Signos Vitales (Usando st.metric)
                    with st.expander("Signos Vitales"):
                        signos_vitales_data = informacion_medica.get("SignosVitales", {})
                        if isinstance(signos_vitales_data, dict) and signos_vitales_data:
                            num_sv = len(signos_vitales_data)
                            cols_sv = st.columns(min(num_sv, 6)) # Máximo 6 columnas para SV
                            i = 0
                            sv_order = ["TAS", "TAD", "FC", "PESO", "Size", "IMC"] # Orden preferido
                            displayed_keys = set()
                            # Mostrar en orden preferido
                            for key in sv_order:
                                if key in signos_vitales_data:
                                    value = signos_vitales_data[key]
                                    display_value = str(value) if str(value).upper() != "NO_ENCONTRADO" and value is not None else "---"
                                    with cols_sv[i % min(num_sv, 6)]:
                                        st.metric(label=key, value=display_value)
                                    displayed_keys.add(key)
                                    i += 1
                            # Mostrar claves restantes
                            extra_keys = [k for k in signos_vitales_data if k not in displayed_keys]
                            for key in extra_keys:
                                value = signos_vitales_data[key]
                                display_value = str(value) if str(value).upper() != "NO_ENCONTRADO" and value is not None else "---"
                                with cols_sv[i % min(num_sv, 6)]:
                                    st.metric(label=key, value=display_value)
                                i += 1
                        else:
                            st.info("No se encontraron datos de Signos Vitales.")

                    # SECCION: Exámenes
                    with st.expander("Exámenes Solicitados/Resultados"):
                        examenes_data = informacion_medica.get("Examenes", [])
                        if isinstance(examenes_data, list):
                            if examenes_data:
                                for examen_dict in examenes_data:
                                    if isinstance(examen_dict, dict):
                                        name = examen_dict.get("Name", "N/E")
                                        resultado = examen_dict.get("Resultado", "N/E")
                                        unidad = examen_dict.get("UnidadMedida", "")
                                        display_text = f"- **{name}:** {resultado}"
                                        if unidad and str(unidad).upper() != "NO_ENCONTRADO": display_text += f" {unidad}"
                                        st.markdown(display_text)
                                    else: st.warning(f"Elemento inesperado en Examenes: {examen_dict}")
                            else: st.info("No se especificaron exámenes.")
                        else: st.warning(f"Formato inesperado para Examenes: {type(examenes_data)}")

                    # SECCION: Diagnósticos
                    with st.expander("Diagnósticos"):
                        diagnosticos_data = informacion_medica.get("Diagnosticos", [])
                        if isinstance(diagnosticos_data, list):
                            if diagnosticos_data:
                                for diag_dict in diagnosticos_data:
                                    if isinstance(diag_dict, dict):
                                        nombre_diag = diag_dict.get("Nombre", "N/E")
                                        diag_id = diag_dict.get("ID", "")
                                        display_text = f"- **{nombre_diag}**"
                                        if diag_id and str(diag_id).strip().upper() != "NO_ENCONTRADO": display_text += f" (ID: {diag_id})"
                                        st.markdown(display_text)
                                    else: st.warning(f"Elemento inesperado en Diagnosticos: {diag_dict}")
                            else: st.info("No se especificaron diagnósticos.")
                        else: st.warning(f"Formato inesperado para Diagnosticos: {type(diagnosticos_data)}")

                    # SECCION: Medicamentos
                    with st.expander("Medicamentos Indicados"):
                        medicamentos_data = informacion_medica.get("Medicinas", [])
                        if isinstance(medicamentos_data, list):
                            if medicamentos_data:
                                for i, med_dict in enumerate(medicamentos_data):
                                    if isinstance(med_dict, dict):
                                        nombre = med_dict.get("Nombre", f"Med_{i+1}")
                                        presentacion = med_dict.get("Presentacion", "")
                                        dosis = med_dict.get("Dosis", "N/E")
                                        st.markdown(f"**{nombre}** {f'({presentacion})' if presentacion else ''}")
                                        st.text_area(f"Dosis_{i}_disp", value=dosis, key=f"med_dosis_disp_{i}", height=68, label_visibility="collapsed", disabled=True)
                                        if i < len(medicamentos_data) - 1: st.divider() # Separador entre meds
                                    else: st.warning(f"Elemento inesperado en Medicinas: {med_dict}")
                            else: st.info("No se especificaron medicamentos.")
                        else: st.warning(f"Formato inesperado para Medicinas: {type(medicamentos_data)}")

                    # SECCION: Plan de Acción
                    with st.expander("Plan de Acción"):
                        plan_data = informacion_medica.get("PlanDeAccion", [])
                        if isinstance(plan_data, list):
                            if plan_data:
                                items_markdown = []
                                for item_dict in plan_data:
                                    if isinstance(item_dict, dict) and len(item_dict) == 1:
                                        instruccion = list(item_dict.values())[0]
                                        if instruccion: items_markdown.append(f"- {instruccion}")
                                    elif isinstance(item_dict, str) and item_dict: # Acepta strings directamente
                                        items_markdown.append(f"- {item_dict}")
                                if items_markdown: st.markdown("\n".join(items_markdown))
                                else: st.info("Plan de acción vacío o con formato no reconocido.")
                            else: st.info("No se especificó plan de acción.")
                        elif isinstance(plan_data, str) and plan_data: # Acepta string simple
                             st.markdown(f"Plan: {plan_data}")
                        else: st.warning(f"Formato inesperado o vacío para PlanDeAccion: {type(plan_data)}")


                    # SECCION: Días de Reposo
                    with st.expander("Indicación de Reposo"):
                        dias_reposo_val = str(informacion_medica.get("DiasReposo", "NO_ENCONTRADO"))
                        if dias_reposo_val.upper() != "NO_ENCONTRADO" and dias_reposo_val.strip():
                             if dias_reposo_val.isdigit():
                                st.metric("Días de Reposo Indicados", value=dias_reposo_val)
                             else: # Si no es número, muestra el texto
                                st.write(f"Indicación: {dias_reposo_val}")
                        else:
                            st.info("No se especificó indicación de reposo.")

                    # SECCION: Comentarios y Literal
                    with st.expander("Comentarios del Modelo y Transcripción Completa", expanded=False): # Inicia cerrado
                        col_comm, col_lit = st.columns(2)
                        with col_comm:
                            st.subheader("Comentarios del Modelo")
                            st.text_area("Comentarios_disp", value=informacion_medica.get("ComentariosModelo", ""), height=300, label_visibility="collapsed", disabled=True, key="comm_mod_disp")
                        with col_lit:
                            st.subheader("Transcripción Literal")
                            st.text_area("Literal_disp", value=informacion_medica.get("Literal", "Transcripción no encontrada en el JSON"), height=300, label_visibility="collapsed", disabled=True, key="lit_tx_disp")

                # Mensaje si el JSON se parseó pero no tiene la estructura esperada
                elif parsed_json and "message" in parsed_json:
                    st.error(f"Error en la respuesta JSON del modelo: {parsed_json.get('message', 'Mensaje no encontrado')}")
                else:
                    st.error("El JSON generado por el modelo no tiene la estructura esperada (status, data, existing-mrs).")
                    # st.json(parsed_json if parsed_json else {"error": "No se pudo parsear JSON"}) # Opcional

            except Exception as display_e:
                # Error durante la visualización de los datos del JSON
                st.error(f"Ocurrió un error al mostrar los datos del JSON: {display_e}")
                st.exception(display_e) # Muestra traceback completo
                # st.write("JSON problemático:") # Opcional
                # st.json(parsed_json)

        # Mensajes si no hay JSON para mostrar
        elif generation_successful: # La generación fue exitosa pero el parseo falló
             st.error("No se pudo mostrar la información porque el JSON generado por el modelo no es válido o no se pudo extraer.")
        else: # La generación misma falló
            st.warning("No hay información para mostrar debido a errores en pasos anteriores (subida, generación, etc.).")

    # Mensajes si el botón se presionó pero faltaban requisitos
    elif not uploaded_file:
        st.warning("Por favor, sube un archivo de audio primero.")
    elif not api_key_configured:
         st.error("La API Key de Gemini no está configurada. No se puede procesar.")

# --- Sección Opcional: Hora Actual ---
st.divider()
try:
    # Intenta obtener hora local de Caracas
    tz = pytz.timezone('America/Caracas')
    current_time_str = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z%z')
except Exception as tz_error:
    # Si falla (ej. pytz no instalado), usa hora local del servidor o UTC
    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + f" (Local/UTC? Error: {tz_error})"

col1, col2 = st.columns([1, 1])
with col1:
    st.caption(f"Hora actual: {current_time_str}")
with col2:
    st.link_button("Ver Historial", "https://docs.google.com/spreadsheets/d/1Unu2MvvBszTVlOz9eu_NPwOBea3xf6R4H9n9vYIoS-w/edit?usp=sharing")
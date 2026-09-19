# QuizForms v0.7 · Online Ready 🌍🌿

Esta versión evita el problema de compartir accidentalmente enlaces `localhost` y añade un asistente de publicación.

## Cambios principales

- Detecta si QuizForms está en una URL pública o en localhost/red privada.
- Los enlaces locales se etiquetan claramente como **NO compartibles**.
- No genera un QR para compañeros mientras la app siga en modo local.
- Nueva pestaña **🌍 Publicar** con diagnóstico de URL y base de datos.
- Soporte opcional para `[app].public_url` en Streamlit Secrets.
- Mantiene el diseño cozy, temporizador, navegación pregunta por pregunta, corrección manual, puntajes, CSV, QR público, contraseña y PIN.
- Mantiene SQLite para desarrollo y Supabase para producción.

## Ejecutar localmente

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

En local verás `🏠 modo local · no compartir`. Esto es intencional.

## Publicación recomendada

1. Sube los archivos del proyecto a GitHub.
2. Crea un proyecto en Supabase.
3. Ejecuta `supabase_setup.sql`.
4. Despliega `app.py` desde Streamlit Community Cloud.
5. En **Advanced settings → Secrets** pega:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
secret_key = "sb_secret_REEMPLAZAR"
```

Opcionalmente:

```toml
[app]
public_url = "https://TU-APP.streamlit.app"
```

## Nunca subir a GitHub

- `.streamlit/secrets.toml`
- `quizforms.db`
- claves secretas de Supabase

## Comprobación final

En la pestaña **🌍 Publicar** debe aparecer:

- `Acceso web: Público ✅`
- `Base de datos: Supabase ☁️`

Solo entonces comparte los enlaces o QR generados por QuizForms.

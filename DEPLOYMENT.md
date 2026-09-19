# Publicar QuizForms v0.7

## Antes de compartir

En la pestaña `🌍 Publicar`, el objetivo es ver:

- `Acceso web: Público ✅`
- `Base de datos: Supabase ☁️`

Si dice `Solo local 🏠`, ningún enlace `localhost` debe enviarse a tus compañeros.

## GitHub

Sube los archivos descomprimidos del proyecto. No subas:

- `quizforms.db`
- `.streamlit/secrets.toml`
- claves privadas

## Supabase

1. Crea un proyecto.
2. Abre SQL Editor.
3. Ejecuta `supabase_setup.sql`.
4. Obtén la Project URL y una Secret Key de servidor.

## Streamlit Community Cloud

1. Entra a https://share.streamlit.io
2. Crea una app desde tu repositorio.
3. Archivo principal: `app.py`.
4. En Advanced settings > Secrets pega:

```toml
[supabase]
url = "https://TU-PROYECTO.supabase.co"
secret_key = "sb_secret_REEMPLAZAR"
```

`[app].public_url` normalmente no hace falta. QuizForms detecta la URL pública. Si deseas fijarla:

```toml
[app]
public_url = "https://TU-APP.streamlit.app"
```

## Prueba final

1. Abre la URL `streamlit.app` desde tu celular usando datos móviles.
2. Crea un formulario pequeño.
3. Copia su enlace público.
4. Ábrelo en una ventana privada.
5. Envía un intento.
6. Comprueba que aparezca en `Panel del creador`.

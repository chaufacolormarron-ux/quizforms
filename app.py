import csv
import io
import os
import random
import secrets
import time
import ipaddress
from urllib.parse import urlsplit, urlunsplit
from collections import defaultdict

import qrcode
import streamlit as st

from parser import parse_questions
from backend import (
    init_storage,
    storage_mode,
    create_quiz,
    get_quiz,
    save_attempt,
    get_attempts,
    attempt_exists,
    verify_admin_pin,
    verify_access_password,
    update_quiz_settings,
    update_attempt_grading,
    storage_healthcheck,
)

st.set_page_config(
    page_title="QuizForms",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_storage()

PREMISE_OPTIONS = {
    "A": "Solo la premisa A es verdadera",
    "B": "Solo la premisa B es verdadera",
    "C": "Ambas premisas son verdaderas",
    "D": "Ambas premisas son falsas",
}


# =========================================================
# ESTILO COZY
# =========================================================
st.markdown(
    """
    <style>
    .block-container {
        max-width: 980px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }

    [data-testid="stHeader"] {
        background: rgba(251, 248, 243, 0.88);
        backdrop-filter: blur(10px);
    }

    h1, h2, h3 {
        letter-spacing: -0.025em;
    }

    .qf-hero {
        padding: 1.45rem 1.6rem;
        border: 1px solid #DED4C7;
        border-radius: 24px;
        background:
            radial-gradient(circle at top right, #E7EFE4 0, transparent 34%),
            linear-gradient(145deg, #FFFDFC, #F5EEE6);
        box-shadow: 0 12px 35px rgba(91, 78, 64, 0.07);
        margin-bottom: 1.2rem;
    }

    .qf-eyebrow {
        color: #647B63;
        font-size: .82rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }

    .qf-title {
        color: #2F352F;
        font-size: 2rem;
        font-weight: 750;
        line-height: 1.15;
        margin: 0;
    }

    .qf-subtitle {
        color: #6E746D;
        margin-top: .6rem;
        margin-bottom: 0;
        font-size: 1rem;
    }

    .qf-pill {
        display: inline-block;
        padding: .35rem .7rem;
        margin: .15rem .2rem .15rem 0;
        background: #E8EEE5;
        color: #4F6650;
        border: 1px solid #D3DDD0;
        border-radius: 999px;
        font-size: .82rem;
        font-weight: 650;
    }

    .qf-soft {
        color: #777B75;
        font-size: .92rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid #E1D8CC;
        background: #FFFCF8;
        padding: .8rem 1rem;
        border-radius: 18px;
        box-shadow: 0 5px 18px rgba(91, 78, 64, 0.045);
    }

    div[data-testid="stExpander"],
    div[data-testid="stForm"] {
        border-radius: 18px !important;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stLinkButton"] a {
        min-height: 2.75rem;
        font-weight: 650;
    }

    .qf-question-number {
        color: #738272;
        font-weight: 700;
        font-size: .9rem;
        margin-bottom: .3rem;
    }

    .qf-question-title {
        font-size: 1.35rem;
        line-height: 1.4;
        font-weight: 720;
        color: #303630;
        margin-bottom: .4rem;
    }

    .qf-reviewed {
        color: #8A714C;
        font-weight: 650;
    }

    @media (max-width: 700px) {
        .block-container {
            padding: 1rem .85rem 4rem .85rem;
        }

        .qf-hero {
            padding: 1.1rem 1rem;
            border-radius: 20px;
        }

        .qf-title {
            font-size: 1.65rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# HELPERS
# =========================================================
def hero(title, subtitle="", eyebrow="QUIZFORMS"):
    st.markdown(
        f"""
        <div class="qf-hero">
            <div class="qf-eyebrow">{eyebrow}</div>
            <div class="qf-title">{title}</div>
            <p class="qf-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def configured_public_url():
    """Optional explicit public URL from environment or Streamlit secrets."""
    env_url = os.getenv("QUIZFORMS_PUBLIC_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    try:
        if "app" in st.secrets:
            value = str(st.secrets["app"].get("public_url", "")).strip()
            if value:
                return value.rstrip("/")
    except Exception:
        pass

    return None


def current_base_url():
    """Current app URL without query string or fragment."""
    try:
        raw = str(st.context.url)
        parts = urlsplit(raw)
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")
    except Exception:
        return "http://localhost:8501"


def get_base_url():
    return configured_public_url() or current_base_url()


def url_is_public(url):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()

        if not host or host == "localhost" or host.endswith(".local"):
            return False

        try:
            ip = ipaddress.ip_address(host)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
            )
        except ValueError:
            return "." in host
    except Exception:
        return False


def get_share_link(code):
    return f"{get_base_url()}/?quiz={code}"


def sharing_status():
    base = get_base_url()
    return {
        "base_url": base,
        "public": url_is_public(base),
        "source": "configured" if configured_public_url() else "detected",
    }


def normalize_questions(questions):
    normalized = []

    for idx, q in enumerate(questions, start=1):
        item = dict(q)
        item["qid"] = str(item.get("qid") or idx)

        try:
            item["points"] = float(item.get("points", 1))
        except (TypeError, ValueError):
            item["points"] = 1.0

        if item["points"] <= 0:
            item["points"] = 1.0

        normalized.append(item)

    return normalized


def fmt_points(value):
    value = float(value or 0)
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def make_qr_png(link):
    qr = qrcode.QRCode(version=None, box_size=8, border=3)
    qr.add_data(link)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def question_order(quiz_code, questions, shuffle_enabled):
    questions = normalize_questions(questions)

    if not shuffle_enabled:
        return questions

    key = f"order_{quiz_code}"
    by_id = {q["qid"]: q for q in questions}

    if key not in st.session_state:
        ids = list(by_id.keys())
        random.shuffle(ids)
        st.session_state[key] = ids

    return [
        by_id[qid]
        for qid in st.session_state[key]
        if qid in by_id
    ]


def option_data(quiz_code, q, shuffle_enabled):
    raw = list(q.get("options", {}).items())

    if not shuffle_enabled:
        return [(key, f"{key}) {text}") for key, text in raw]

    state_key = f"option_order_{quiz_code}_{q['qid']}"

    if state_key not in st.session_state:
        shuffled = raw[:]
        random.shuffle(shuffled)
        st.session_state[state_key] = shuffled

    visible_letters = ["A", "B", "C", "D", "E", "F"]
    result = []

    for idx, (original_key, text) in enumerate(
        st.session_state[state_key]
    ):
        visible = (
            visible_letters[idx]
            if idx < len(visible_letters)
            else str(idx + 1)
        )
        result.append((original_key, f"{visible}) {text}"))

    return result


def answer_key(quiz_code, qid):
    return f"ans_{quiz_code}_{qid}"


def collect_answers(quiz_code, questions):
    answers = {}

    for q in questions:
        value = st.session_state.get(
            answer_key(quiz_code, q["qid"]),
            "",
        )

        if value is None:
            value = ""

        answers[q["qid"]] = str(value).strip()

    return answers


def answered_count(answers):
    return sum(1 for value in answers.values() if str(value).strip())


def auto_grade_question(q, user_answer):
    expected = str(q.get("answer", "")).strip()
    user_answer = str(user_answer).strip()
    points = float(q.get("points", 1))

    if q["type"] in ["multiple_choice", "true_false", "premises"]:
        correct = user_answer.casefold() == expected.casefold()
        return {
            "grading": "auto",
            "is_correct": correct,
            "awarded_points": points if correct else 0.0,
        }

    if q["type"] in ["written", "doctor", "definition"]:
        keywords = q.get("keywords", [])

        if keywords:
            normalized = user_answer.casefold()
            hits = sum(
                1 for keyword in keywords
                if keyword.casefold() in normalized
            )
            needed = max(1, (len(keywords) + 1) // 2)
            correct = hits >= needed

            return {
                "grading": "auto",
                "is_correct": correct,
                "awarded_points": points if correct else 0.0,
            }

    return {
        "grading": "manual",
        "is_correct": None,
        "awarded_points": None,
    }


def summarize_attempt(details):
    total_points = sum(float(d.get("max_points", 1)) for d in details)

    awarded_points = sum(
        float(d.get("awarded_points") or 0)
        for d in details
        if d.get("awarded_points") is not None
    )

    pending = sum(
        1
        for d in details
        if d.get("awarded_points") is None
    )

    graded_count = sum(
        1
        for d in details
        if d.get("awarded_points") is not None
    )

    fully_correct = sum(
        1
        for d in details
        if d.get("is_correct") is True
    )

    score = None

    if pending == 0 and total_points > 0:
        score = round((awarded_points / total_points) * 20, 2)

    return {
        "total_points": round(total_points, 2),
        "awarded_points": round(awarded_points, 2),
        "pending": pending,
        "graded_count": graded_count,
        "fully_correct": fully_correct,
        "score": score,
    }


def attempts_to_csv(attempts):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Nombre",
            "Puntos obtenidos",
            "Puntos totales",
            "Pendientes",
            "Nota / 20",
            "Fecha",
        ]
    )

    for attempt in attempts:
        summary = summarize_attempt(attempt["details"])
        writer.writerow(
            [
                attempt["student_name"],
                summary["awarded_points"],
                summary["total_points"],
                summary["pending"],
                summary["score"],
                attempt["created_at"],
            ]
        )

    return output.getvalue().encode("utf-8-sig")


def build_question_analytics(quiz, attempts):
    questions = normalize_questions(quiz["questions"])
    stats = {}

    for idx, q in enumerate(questions, start=1):
        stats[q["qid"]] = {
            "N°": idx,
            "Pregunta": q.get("question", ""),
            "Tipo": q["type"],
            "Puntos": q.get("points", 1),
            "Respondidas": 0,
            "Calificadas": 0,
            "Puntos obtenidos": 0.0,
            "Puntos posibles": 0.0,
        }

    for attempt in attempts:
        for detail in attempt["details"]:
            qid = str(detail.get("qid", ""))

            if qid not in stats:
                continue

            stats[qid]["Respondidas"] += 1

            if detail.get("awarded_points") is not None:
                stats[qid]["Calificadas"] += 1
                stats[qid]["Puntos obtenidos"] += float(
                    detail.get("awarded_points") or 0
                )
                stats[qid]["Puntos posibles"] += float(
                    detail.get("max_points", 1)
                )

    rows = []

    for row in stats.values():
        possible = row["Puntos posibles"]
        row["% rendimiento"] = (
            round((row["Puntos obtenidos"] / possible) * 100, 1)
            if possible > 0
            else None
        )
        row["Puntos obtenidos"] = round(row["Puntos obtenidos"], 2)
        row["Puntos posibles"] = round(row["Puntos posibles"], 2)
        rows.append(row)

    return rows


def render_question_preview(q):
    with st.container(border=True):
        st.markdown(
            f"**{q.get('question', '')}**  \n"
            f"<span class='qf-soft'>"
            f"{q['type']} · {fmt_points(q.get('points', 1))} pts"
            f"</span>",
            unsafe_allow_html=True,
        )

        if q["type"] == "multiple_choice":
            for key, value in q.get("options", {}).items():
                st.write(f"{key}) {value}")

        elif q["type"] == "premises":
            st.write("A ·", q.get("premise_a", ""))
            st.write("B ·", q.get("premise_b", ""))

        elif q["type"] == "table":
            if q.get("instruction"):
                st.caption(q["instruction"])
            if q.get("headers"):
                st.write(" | ".join(q["headers"]))
            for row in q.get("rows", []):
                st.code(row)

        if q.get("answer"):
            st.caption(f"Respuesta: {q['answer']}")

        if q.get("keywords"):
            st.caption("Palabras clave: " + ", ".join(q["keywords"]))


def check_quiz_access(quiz_code, quiz):
    settings = quiz.get("settings", {})

    if not settings.get("has_access_password", False):
        return True

    auth_key = f"access_ok_{quiz_code}"

    if st.session_state.get(auth_key):
        return True

    hero(
        "Este examen tiene una llave 🔐",
        "Ingresa la contraseña que te compartió quien creó el formulario.",
        "ACCESO",
    )

    with st.container(border=True):
        password = st.text_input(
            "Contraseña",
            type="password",
            key=f"access_password_{quiz_code}",
        )

        if st.button(
            "Entrar al examen",
            type="primary",
            use_container_width=True,
            key=f"access_button_{quiz_code}",
        ):
            if verify_access_password(quiz_code, password):
                st.session_state[auth_key] = True
                st.rerun()
            else:
                st.error("La contraseña no coincide.")

    return False


@st.fragment(run_every="1s")
def countdown(deadline_key, force_key):
    deadline = st.session_state.get(deadline_key)

    if not deadline:
        return

    remaining = max(0, int(deadline - time.time()))
    minutes, seconds = divmod(remaining, 60)

    if remaining <= 60:
        st.warning(f"⏳ {minutes:02d}:{seconds:02d}")
    else:
        st.markdown(
            f"<span class='qf-pill'>⏳ {minutes:02d}:{seconds:02d}</span>",
            unsafe_allow_html=True,
        )

    if remaining <= 0 and not st.session_state.get(force_key):
        st.session_state[force_key] = True
        st.rerun()


def render_question_widget(quiz_code, q, number, settings):
    st.markdown(
        f"""
        <div class="qf-question-number">
            PREGUNTA {number}
            · {fmt_points(q.get('points', 1))} PTS
        </div>
        <div class="qf-question-title">
            {q.get('question', '')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    key = answer_key(quiz_code, q["qid"])

    if q["type"] == "multiple_choice":
        data = option_data(
            quiz_code,
            q,
            settings.get("shuffle_options", False),
        )
        values = [x[0] for x in data]
        labels = {x[0]: x[1] for x in data}

        st.radio(
            "Elige una respuesta",
            options=values,
            format_func=lambda value, m=labels: m[value],
            index=None,
            key=key,
            label_visibility="collapsed",
        )

    elif q["type"] == "true_false":
        st.radio(
            "Elige una respuesta",
            ["Verdadero", "Falso"],
            index=None,
            key=key,
            horizontal=True,
            label_visibility="collapsed",
        )

    elif q["type"] == "premises":
        with st.container(border=True):
            st.write("**Premisa A**")
            st.write(q.get("premise_a", ""))
            st.write("**Premisa B**")
            st.write(q.get("premise_b", ""))

        keys = list(PREMISE_OPTIONS.keys())

        st.radio(
            "Elige una interpretación",
            options=keys,
            format_func=lambda value: (
                f"{value}) {PREMISE_OPTIONS[value]}"
            ),
            index=None,
            key=key,
            label_visibility="collapsed",
        )

    elif q["type"] == "table":
        if q.get("instruction"):
            st.info(q["instruction"])

        if q.get("headers"):
            st.write("**" + " | ".join(q["headers"]) + "**")

        for row in q.get("rows", []):
            st.code(row)

        st.text_area(
            "Tu respuesta",
            key=key,
            height=150,
            placeholder="Completa aquí la tabla o escribe tu respuesta...",
        )

    else:
        st.text_area(
            "Tu respuesta",
            key=key,
            height=170,
            placeholder="Escribe tu respuesta con calma...",
        )


def submit_attempt(quiz_code, quiz, questions, force=False):
    submit_flag = f"submitted_{quiz_code}"

    if st.session_state.get(submit_flag):
        return

    settings = quiz.get("settings", {})
    answers = collect_answers(quiz_code, questions)

    unanswered = [
        idx + 1
        for idx, q in enumerate(questions)
        if not answers.get(q["qid"], "").strip()
    ]

    if (
        settings.get("require_all_answers", False)
        and unanswered
        and not force
    ):
        st.error(
            "Todavía faltan: "
            + ", ".join(map(str, unanswered))
            + ". Puedes volver a ellas antes de enviar."
        )
        return

    details = []

    for q in questions:
        qid = q["qid"]
        user_answer = answers.get(qid, "")
        grading = auto_grade_question(q, user_answer)

        details.append(
            {
                "qid": qid,
                "question": q.get("question", ""),
                "type": q["type"],
                "user_answer": user_answer,
                "expected": str(q.get("answer", "")).strip(),
                "is_correct": grading["is_correct"],
                "grading": grading["grading"],
                "max_points": float(q.get("points", 1)),
                "awarded_points": grading["awarded_points"],
            }
        )

    summary = summarize_attempt(details)
    student_name = st.session_state.get(
        f"student_name_saved_{quiz_code}",
        "Sin nombre",
    )

    save_attempt(
        quiz_code=quiz_code,
        student_name=student_name,
        answers=answers,
        correct=summary["fully_correct"],
        total=summary["graded_count"],
        score=summary["score"],
        details=details,
    )

    st.session_state[submit_flag] = True
    st.session_state[f"summary_{quiz_code}"] = summary
    st.session_state[f"details_{quiz_code}"] = details
    st.session_state[f"force_submit_{quiz_code}"] = False
    st.rerun()


def render_result_screen(quiz_code, quiz):
    summary = st.session_state.get(f"summary_{quiz_code}", {})
    details = st.session_state.get(f"details_{quiz_code}", [])
    settings = quiz.get("settings", {})

    hero(
        "Tu intento quedó guardado 🌱",
        "Ya puedes cerrar esta página con tranquilidad.",
        "TERMINASTE",
    )

    if summary.get("pending", 0) > 0:
        st.info(
            f"{summary['pending']} respuesta(s) necesitan revisión manual."
        )

        if settings.get("show_score", True):
            st.metric(
                "Puntos confirmados",
                f"{fmt_points(summary.get('awarded_points', 0))}/"
                f"{fmt_points(summary.get('total_points', 0))}",
            )

    elif settings.get("show_score", True):
        c1, c2 = st.columns(2)
        c1.metric("Nota", f"{summary.get('score', '—')}/20")
        c2.metric(
            "Puntos",
            f"{fmt_points(summary.get('awarded_points', 0))}/"
            f"{fmt_points(summary.get('total_points', 0))}",
        )
    else:
        st.success("Tu respuesta fue registrada correctamente.")

    if settings.get("show_feedback", False):
        st.markdown("### Revisión")
        for idx, detail in enumerate(details, start=1):
            with st.container(border=True):
                st.write(f"**{idx}. {detail['question']}**")
                st.write("Tu respuesta:", detail.get("user_answer") or "—")

                if detail.get("is_correct") is True:
                    st.success("Correcta")
                elif detail.get("is_correct") is False:
                    st.error(
                        "Incorrecta · "
                        f"Respuesta esperada: {detail.get('expected', '—')}"
                    )
                else:
                    st.warning("Pendiente de corrección manual.")


def render_student_quiz(quiz_code, direct_mode=False):
    quiz = get_quiz(quiz_code)

    if not quiz:
        hero(
            "No encontré ese formulario",
            "Revisa el código o pide nuevamente el enlace.",
            "UPS",
        )
        return

    settings = quiz.get("settings", {})

    if not settings.get("is_open", True):
        hero(
            "Este examen está cerrado 🌙",
            "El formulario existe, pero ya no está recibiendo respuestas.",
            "CERRADO",
        )
        return

    if not check_quiz_access(quiz_code, quiz):
        return

    questions = question_order(
        quiz_code,
        quiz["questions"],
        settings.get("shuffle_questions", False),
    )

    if st.session_state.get(f"submitted_{quiz_code}"):
        render_result_screen(quiz_code, quiz)
        return

    started_key = f"started_{quiz_code}"
    saved_name_key = f"student_name_saved_{quiz_code}"
    deadline_key = f"deadline_{quiz_code}"
    force_key = f"force_submit_{quiz_code}"

    if not st.session_state.get(started_key):
        total_points = sum(float(q.get("points", 1)) for q in questions)
        timer_minutes = int(settings.get("timer_minutes", 0) or 0)

        hero(
            quiz["title"],
            settings.get("instructions", "")
            or "Un espacio tranquilo para responder a tu ritmo.",
            "LISTO PARA EMPEZAR",
        )

        st.markdown(
            f"<span class='qf-pill'>📝 {len(questions)} preguntas</span>"
            f"<span class='qf-pill'>⭐ {fmt_points(total_points)} puntos</span>"
            + (
                f"<span class='qf-pill'>⏳ {timer_minutes} min</span>"
                if timer_minutes > 0
                else ""
            ),
            unsafe_allow_html=True,
        )

        st.write("")

        with st.container(border=True):
            student_name = st.text_input(
                "Tu nombre y apellido",
                placeholder="Escribe cómo quieres aparecer en resultados",
                key=f"student_name_input_{quiz_code}",
            )

            st.caption(
                "Tus respuestas se irán conservando mientras navegas "
                "entre las preguntas en esta sesión."
            )

            if st.button(
                "🌿 Comenzar examen",
                type="primary",
                use_container_width=True,
                key=f"start_{quiz_code}",
            ):
                if not student_name.strip():
                    st.error("Escribe tu nombre antes de comenzar.")
                    return

                if (
                    not settings.get("allow_multiple_attempts", True)
                    and attempt_exists(quiz_code, student_name.strip())
                ):
                    st.error(
                        "Ya existe un intento con ese nombre "
                        "y este formulario permite solo uno."
                    )
                    return

                st.session_state[saved_name_key] = student_name.strip()
                st.session_state[started_key] = True
                st.session_state[f"current_{quiz_code}"] = 0
                st.session_state[f"review_{quiz_code}"] = []
                st.session_state[f"review_page_{quiz_code}"] = False

                if timer_minutes > 0:
                    st.session_state[deadline_key] = (
                        time.time() + timer_minutes * 60
                    )

                st.rerun()

        return

    # Temporizador
    if settings.get("timer_minutes", 0):
        timer_col, name_col = st.columns([1, 2])
        with timer_col:
            countdown(deadline_key, force_key)
        with name_col:
            st.caption(
                f"Respondiendo como "
                f"**{st.session_state.get(saved_name_key, '')}**"
            )

    if st.session_state.get(force_key):
        submit_attempt(
            quiz_code,
            quiz,
            questions,
            force=True,
        )
        return

    answers = collect_answers(quiz_code, questions)
    answered = answered_count(answers)
    total = len(questions)
    review_ids = set(st.session_state.get(f"review_{quiz_code}", []))

    st.progress(
        answered / total if total else 0,
        text=f"{answered} de {total} respondidas",
    )

    st.markdown(
        f"<span class='qf-pill'>✅ {answered} respondidas</span>"
        f"<span class='qf-pill'>🔖 {len(review_ids)} para revisar</span>",
        unsafe_allow_html=True,
    )

    review_page_key = f"review_page_{quiz_code}"

    if st.session_state.get(review_page_key):
        hero(
            "Revisa antes de enviar ☕",
            "Aquí puedes ver qué falta y volver a cualquier pregunta.",
            "CASI LISTO",
        )

        unanswered = [
            idx + 1
            for idx, q in enumerate(questions)
            if not answers.get(q["qid"], "").strip()
        ]

        c1, c2, c3 = st.columns(3)
        c1.metric("Respondidas", answered)
        c2.metric("Sin responder", len(unanswered))
        c3.metric("Marcadas", len(review_ids))

        if unanswered:
            st.warning(
                "Sin responder: " + ", ".join(map(str, unanswered))
            )

        if review_ids:
            review_numbers = [
                str(idx + 1)
                for idx, q in enumerate(questions)
                if q["qid"] in review_ids
            ]
            st.info(
                "Marcadas para revisar: " + ", ".join(review_numbers)
            )

        jump = st.selectbox(
            "Ir a una pregunta",
            options=list(range(total)),
            format_func=lambda idx: (
                f"Pregunta {idx + 1}"
                + (
                    " · sin responder"
                    if not answers.get(questions[idx]["qid"], "").strip()
                    else " · respondida"
                )
                + (
                    " · 🔖"
                    if questions[idx]["qid"] in review_ids
                    else ""
                )
            ),
            key=f"jump_{quiz_code}",
        )

        a, b = st.columns(2)

        with a:
            if st.button(
                "← Volver a la pregunta elegida",
                use_container_width=True,
            ):
                st.session_state[f"current_{quiz_code}"] = int(jump)
                st.session_state[review_page_key] = False
                st.rerun()

        with b:
            if st.button(
                "📨 Enviar examen",
                type="primary",
                use_container_width=True,
            ):
                submit_attempt(
                    quiz_code,
                    quiz,
                    questions,
                    force=False,
                )

        return

    current_key = f"current_{quiz_code}"
    current = int(st.session_state.get(current_key, 0))
    current = max(0, min(current, total - 1))
    q = questions[current]

    with st.container(border=True):
        render_question_widget(
            quiz_code,
            q,
            current + 1,
            settings,
        )

    qid = q["qid"]
    is_marked = qid in review_ids

    nav1, nav2, nav3 = st.columns([1, 1.15, 1])

    with nav1:
        if st.button(
            "← Anterior",
            disabled=current == 0,
            use_container_width=True,
        ):
            st.session_state[current_key] = current - 1
            st.rerun()

    with nav2:
        if st.button(
            "✓ Quitar marca" if is_marked else "🔖 Revisar luego",
            use_container_width=True,
        ):
            updated = set(review_ids)

            if is_marked:
                updated.discard(qid)
            else:
                updated.add(qid)

            st.session_state[f"review_{quiz_code}"] = list(updated)
            st.rerun()

    with nav3:
        if current < total - 1:
            if st.button(
                "Siguiente →",
                type="primary",
                use_container_width=True,
            ):
                st.session_state[current_key] = current + 1
                st.rerun()
        else:
            if st.button(
                "Revisar y enviar →",
                type="primary",
                use_container_width=True,
            ):
                st.session_state[review_page_key] = True
                st.rerun()

    with st.expander("🗺️ Mapa del examen"):
        jump = st.selectbox(
            "Saltar a",
            options=list(range(total)),
            index=current,
            format_func=lambda idx: (
                f"{'✅' if answers.get(questions[idx]['qid'], '').strip() else '○'} "
                f"Pregunta {idx + 1}"
                f"{' · 🔖' if questions[idx]['qid'] in review_ids else ''}"
            ),
            key=f"map_jump_{quiz_code}",
        )

        if st.button(
            "Ir a esa pregunta",
            use_container_width=True,
            key=f"map_go_{quiz_code}",
        ):
            st.session_state[current_key] = int(jump)
            st.rerun()

        if st.button(
            "📋 Revisar todo antes de enviar",
            use_container_width=True,
            key=f"review_all_{quiz_code}",
        ):
            st.session_state[review_page_key] = True
            st.rerun()


# =========================================================
# DIRECT LINK
# =========================================================
direct_quiz_code = str(
    st.query_params.get("quiz", "")
).strip().upper()

if direct_quiz_code:
    render_student_quiz(direct_quiz_code, direct_mode=True)

    if not st.session_state.get(f"started_{direct_quiz_code}"):
        if st.button("← Inicio de QuizForms"):
            st.query_params.clear()
            st.rerun()

    st.stop()


# =========================================================
# HOME / CREATOR
# =========================================================
hero(
    "QuizForms 🌿",
    "Convierte tus bancos de preguntas en formularios compartibles, "
    "bonitos y fáciles de resolver.",
    "VERSIÓN 0.7 · ONLINE READY",
)

mode_label = (
    "☁️ Supabase conectado"
    if storage_mode() == "supabase"
    else "💻 SQLite local"
)

_share = sharing_status()
share_label = (
    "🌍 enlace público listo"
    if _share["public"]
    else "🏠 modo local · no compartir"
)

st.markdown(
    f"<span class='qf-pill'>{mode_label}</span>"
    f"<span class='qf-pill'>{share_label}</span>"
    "<span class='qf-pill'>🫖 interfaz cozy</span>"
    "<span class='qf-pill'>🧭 pregunta por pregunta</span>",
    unsafe_allow_html=True,
)

if not _share["public"]:
    st.warning(
        "Estás usando QuizForms de forma local. Los enlaces con localhost o una IP privada "
        "solo funcionan en tu PC o red local. Para compartir con tus compañeros, usa la pestaña "
        "🌍 Publicar."
    )

st.write("")

tab_create, tab_solve, tab_creator, tab_publish = st.tabs(
    [
        "🌱 Crear",
        "✍️ Resolver",
        "🔐 Panel del creador",
        "🌍 Publicar",
    ]
)



with tab_create:
    st.subheader("Crear un nuevo formulario")

    with st.container(border=True):
        quiz_title = st.text_input(
            "Título",
            placeholder="Ej. Enzimas III · Simulacro",
        )

        instructions = st.text_area(
            "Mensaje para tus compañeros",
            placeholder=(
                "Ej. Responde con calma. "
                "Puedes marcar preguntas para revisarlas antes de enviar."
            ),
            height=85,
        )

        uploaded = st.file_uploader(
            "Subir TXT de QuizApp",
            type=["txt"],
            key="quiz_txt_uploader_v061",
        )

    default_text = """1. ¿Cuál es el efecto de un inhibidor competitivo sobre la Km aparente?
A) Disminuye
B) Aumenta
C) No cambia
D) Se vuelve cero
Respuesta: B
Puntos: 1

Tipo: Doctor
Pregunta: Explica por qué puede superarse una inhibición competitiva aumentando la concentración de sustrato.
Respuesta: Porque el sustrato y el inhibidor compiten por el mismo sitio activo.
Puntos: 3
Fin pregunta
"""

    if "questions_text_v061" not in st.session_state:
        st.session_state["questions_text_v061"] = default_text

    if "uploaded_signature_v061" not in st.session_state:
        st.session_state["uploaded_signature_v061"] = None

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        signature = (uploaded.name, len(file_bytes), hash(file_bytes))

        if st.session_state["uploaded_signature_v061"] != signature:
            try:
                decoded = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    decoded = file_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    decoded = file_bytes.decode("latin-1")

            st.session_state["questions_text_v061"] = decoded
            st.session_state["uploaded_signature_v061"] = signature
            st.session_state.pop("preview_v061", None)
            st.session_state.pop("parse_error_v061", None)

    raw_text = st.text_area(
        "Preguntas",
        key="questions_text_v061",
        height=360,
        help=(
            "Puedes pegar tus preguntas aquí o subir un TXT. "
            "El botón de abajo leerá exactamente este contenido."
        ),
    )

    st.subheader("Cómo quieres que se sienta el examen")

    with st.container(border=True):
        c1, c2 = st.columns(2)

        with c1:
            show_score = st.toggle(
                "Mostrar nota al terminar",
                value=True,
                key="show_score_v061",
            )

            show_feedback = st.toggle(
                "Mostrar corrección al terminar",
                value=False,
                help="Puede revelar respuestas correctas.",
                key="show_feedback_v061",
            )

            shuffle_questions = st.toggle(
                "Mezclar preguntas",
                value=False,
                key="shuffle_questions_v061",
            )

            require_all_answers = st.toggle(
                "Exigir todas las respuestas",
                value=True,
                key="require_all_v061",
            )

        with c2:
            shuffle_options = st.toggle(
                "Mezclar alternativas",
                value=False,
                key="shuffle_options_v061",
            )

            allow_multiple_attempts = st.toggle(
                "Permitir varios intentos",
                value=False,
                key="multiple_attempts_v061",
            )

            timer_minutes = st.number_input(
                "Tiempo límite en minutos · 0 = sin límite",
                min_value=0,
                max_value=300,
                value=0,
                step=5,
                key="timer_minutes_v061",
            )

            access_password = st.text_input(
                "Contraseña para alumnos · opcional",
                type="password",
                key="access_password_v061",
            )

    if "generated_admin_pin_v061" not in st.session_state:
        st.session_state["generated_admin_pin_v061"] = str(
            secrets.randbelow(900000) + 100000
        )

    admin_pin = st.text_input(
        "PIN privado del creador",
        value=st.session_state["generated_admin_pin_v061"],
        type="password",
        key="admin_pin_v061",
    )

    if st.button(
        "✨ Leer mis preguntas",
        type="primary",
        use_container_width=True,
        key="read_questions_v061",
    ):
        st.session_state.pop("parse_error_v061", None)

        try:
            cleaned = (raw_text or "").strip()

            if not cleaned:
                st.session_state["preview_v061"] = []
                st.session_state["parse_error_v061"] = (
                    "El cuadro de preguntas está vacío."
                )
            else:
                parsed_questions = normalize_questions(
                    parse_questions(cleaned)
                )
                st.session_state["preview_v061"] = parsed_questions

                if not parsed_questions:
                    st.session_state["parse_error_v061"] = (
                        "No pude reconocer ninguna pregunta. "
                        "Comprueba que el archivo use formatos como "
                        "'1. Pregunta', 'Respuesta:', 'Tipo:', "
                        "'Palabra:' o 'Fin pregunta'."
                    )

        except Exception as exc:
            st.session_state["preview_v061"] = []
            st.session_state["parse_error_v061"] = (
                f"Error al leer las preguntas: {type(exc).__name__}: {exc}"
            )

    parse_error = st.session_state.get("parse_error_v061")
    questions = st.session_state.get("preview_v061", [])

    if parse_error:
        st.error(parse_error)

        with st.expander("🔎 Ver diagnóstico del texto"):
            lines = [
                line
                for line in (raw_text or "").splitlines()
                if line.strip()
            ]
            st.write(f"**Líneas con contenido:** {len(lines)}")

            if lines:
                st.write("**Primeras líneas detectadas:**")
                st.code("\\n".join(lines[:20]))

            st.caption(
                "Si este diagnóstico aparece con contenido correcto, "
                "el problema ya no queda oculto: podremos adaptar el parser "
                "al formato exacto del TXT."
            )

    if questions:
        total_points = sum(float(q.get("points", 1)) for q in questions)

        st.success(
            f"✨ ¡Listo! Detecté {len(questions)} preguntas "
            f"con {fmt_points(total_points)} puntos en total."
        )

        counts = defaultdict(int)
        for q in questions:
            counts[q["type"]] += 1

        cols = st.columns(min(max(len(counts), 1), 5))
        for idx, (qtype, count) in enumerate(counts.items()):
            cols[idx % len(cols)].metric(qtype, count)

        with st.expander("👀 Vista previa del examen", expanded=True):
            for idx, q in enumerate(questions, start=1):
                st.caption(f"Pregunta detectada #{idx}")
                render_question_preview(q)

        if st.button(
            "🌿 Crear y generar enlace",
            type="primary",
            use_container_width=True,
            key="create_form_v061",
        ):
            if not quiz_title.strip():
                st.error("Ponle un título al formulario.")
            elif not admin_pin.strip():
                st.error("Define un PIN del creador.")
            else:
                code = secrets.token_hex(3).upper()

                settings = {
                    "is_open": True,
                    "instructions": instructions.strip(),
                    "show_score": show_score,
                    "show_feedback": show_feedback,
                    "shuffle_questions": shuffle_questions,
                    "shuffle_options": shuffle_options,
                    "allow_multiple_attempts": allow_multiple_attempts,
                    "require_all_answers": require_all_answers,
                    "has_access_password": bool(access_password.strip()),
                    "timer_minutes": int(timer_minutes),
                    "question_by_question": True,
                }

                create_quiz(
                    code=code,
                    title=quiz_title.strip(),
                    questions=questions,
                    admin_pin=admin_pin.strip(),
                    access_password=access_password.strip() or None,
                    settings=settings,
                )

                share_link = get_share_link(code)
                share_info = sharing_status()

                st.balloons()

                if share_info["public"]:
                    hero(
                        "Formulario listo para compartir ✨",
                        "Tu app está en una URL pública. Comparte el enlace o el QR con tus compañeros. "
                        "Guarda tu PIN para revisar resultados.",
                        "CREADO · ONLINE",
                    )
                else:
                    hero(
                        "Formulario creado para prueba local 🌱",
                        "Funciona en esta computadora, pero el enlace aún no es público. "
                        "Publícalo antes de enviarlo a tus compañeros.",
                        "CREADO · LOCAL",
                    )

                a, b = st.columns(2)
                a.metric("Código", code)
                b.metric("PIN creador", admin_pin.strip())

                st.code(share_link)

                if share_info["public"]:
                    qr_png = make_qr_png(share_link)
                    x, y = st.columns(2)

                    with x:
                        st.link_button(
                            "Abrir como alumno ↗",
                            share_link,
                            use_container_width=True,
                        )

                    with y:
                        st.download_button(
                            "Descargar QR",
                            data=qr_png,
                            file_name=f"quiz_{code}_qr.png",
                            mime="image/png",
                            use_container_width=True,
                        )

                    st.image(qr_png, width=210)
                else:
                    st.warning(
                        "⚠️ No envíes este enlace todavía. Es un enlace local y tus amigos no podrán abrirlo."
                    )
                    st.link_button(
                        "Abrir prueba local ↗",
                        share_link,
                        use_container_width=True,
                    )
                    st.info(
                        "Ve a **🌍 Publicar** para dejar QuizForms disponible por Internet. "
                        "Cuando la app esté desplegada, los nuevos enlaces y QR serán públicos."
                    )


with tab_solve:
    st.subheader("Entrar a un formulario")

    with st.container(border=True):
        quiz_code = st.text_input(
            "Código del formulario",
            placeholder="Ej. A1B2C3",
            key="solve_code",
        ).strip().upper()

        if st.button(
            "Abrir examen",
            type="primary",
            use_container_width=True,
            key="solve_open",
        ):
            if quiz_code:
                st.query_params["quiz"] = quiz_code
                st.rerun()


with tab_creator:
    st.subheader("Panel del creador")

    with st.container(border=True):
        result_code = st.text_input(
            "Código",
            placeholder="Ej. A1B2C3",
            key="results_code",
        ).strip().upper()

        result_pin = st.text_input(
            "PIN del creador",
            type="password",
            key="results_pin",
        )

    if result_code and result_pin:
        quiz = get_quiz(result_code)

        if not quiz:
            st.error("No existe ese formulario.")

        elif not verify_admin_pin(result_code, result_pin):
            st.error("El PIN no coincide.")

        else:
            settings = quiz.get("settings", {})
            attempts = get_attempts(result_code)

            hero(
                quiz["title"],
                "Tu rincón de resultados y corrección.",
                "PANEL DEL CREADOR",
            )

            current_open = settings.get("is_open", True)

            state_col, action_col = st.columns([2, 1])

            with state_col:
                if current_open:
                    st.success("🟢 El examen está abierto.")
                else:
                    st.warning("🌙 El examen está cerrado.")

            with action_col:
                if st.button(
                    "Cerrar examen" if current_open else "Abrir examen",
                    use_container_width=True,
                ):
                    settings["is_open"] = not current_open
                    update_quiz_settings(result_code, settings)
                    st.rerun()

            if not attempts:
                st.info("Todavía no hay respuestas.")
            else:
                summaries = [
                    summarize_attempt(a["details"])
                    for a in attempts
                ]

                final_scores = [
                    s["score"]
                    for s in summaries
                    if s["score"] is not None
                ]

                pending_attempts = sum(
                    1 for s in summaries if s["pending"] > 0
                )

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Intentos", len(attempts))
                c2.metric("Por revisar", pending_attempts)
                c3.metric(
                    "Promedio",
                    (
                        f"{sum(final_scores)/len(final_scores):.2f}/20"
                        if final_scores
                        else "—"
                    ),
                )
                c4.metric(
                    "Mejor nota",
                    f"{max(final_scores):.2f}/20" if final_scores else "—",
                )

                rows = []

                for attempt, summary in zip(attempts, summaries):
                    rows.append(
                        {
                            "Nombre": attempt["student_name"],
                            "Puntos": (
                                f"{fmt_points(summary['awarded_points'])}/"
                                f"{fmt_points(summary['total_points'])}"
                            ),
                            "Pendientes": summary["pending"],
                            "Nota / 20": summary["score"],
                            "Fecha": attempt["created_at"],
                        }
                    )

                st.dataframe(
                    rows,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "⬇️ Descargar resultados CSV",
                    data=attempts_to_csv(attempts),
                    file_name=f"resultados_{result_code}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

                st.subheader("Corrección manual")
                pending_any = False

                for attempt in attempts:
                    manual_details = [
                        (idx, d)
                        for idx, d in enumerate(attempt["details"])
                        if d.get("awarded_points") is None
                    ]

                    if not manual_details:
                        continue

                    pending_any = True

                    with st.expander(
                        f"☕ {attempt['student_name']} · "
                        f"{len(manual_details)} pendiente(s)"
                    ):
                        edited_details = [
                            dict(d) for d in attempt["details"]
                        ]

                        with st.form(f"manual_{attempt['id']}"):
                            for idx, detail in manual_details:
                                max_points = float(
                                    detail.get("max_points", 1)
                                )

                                st.write(f"**{detail['question']}**")
                                st.info(detail.get("user_answer") or "Sin respuesta")

                                if detail.get("expected"):
                                    st.caption(
                                        "Referencia: "
                                        + detail["expected"]
                                    )

                                awarded = st.slider(
                                    "Puntos",
                                    min_value=0.0,
                                    max_value=max_points,
                                    value=0.0,
                                    step=0.25,
                                    key=f"grade_{attempt['id']}_{idx}",
                                )

                                edited_details[idx]["awarded_points"] = float(
                                    awarded
                                )

                                if awarded >= max_points:
                                    edited_details[idx]["is_correct"] = True
                                elif awarded <= 0:
                                    edited_details[idx]["is_correct"] = False
                                else:
                                    edited_details[idx]["is_correct"] = None

                                edited_details[idx]["grading"] = (
                                    "manual_reviewed"
                                )
                                st.divider()

                            save_grades = st.form_submit_button(
                                "Guardar corrección",
                                type="primary",
                                use_container_width=True,
                            )

                        if save_grades:
                            summary = summarize_attempt(edited_details)

                            update_attempt_grading(
                                attempt_id=attempt["id"],
                                details=edited_details,
                                correct=summary["fully_correct"],
                                total=summary["graded_count"],
                                score=summary["score"],
                            )

                            st.success("Corrección guardada 🌿")
                            st.rerun()

                if not pending_any:
                    st.success("Todo está corregido ✨")

                st.subheader("Qué preguntas costaron más")

                analytics = build_question_analytics(quiz, attempts)

                st.dataframe(
                    analytics,
                    use_container_width=True,
                    hide_index=True,
                )

                graded_rows = [
                    row
                    for row in analytics
                    if row["% rendimiento"] is not None
                ]

                if graded_rows:
                    hardest = min(
                        graded_rows,
                        key=lambda row: row["% rendimiento"],
                    )
                    st.info(
                        f"Menor rendimiento: pregunta #{hardest['N°']} "
                        f"· {hardest['% rendimiento']}%"
                    )

                st.subheader("Intentos individuales")

                for attempt in attempts:
                    summary = summarize_attempt(attempt["details"])
                    label = (
                        f"{summary['score']}/20"
                        if summary["score"] is not None
                        else f"{summary['pending']} pendiente(s)"
                    )

                    with st.expander(
                        f"🌱 {attempt['student_name']} · {label}"
                    ):
                        for idx, detail in enumerate(
                            attempt["details"],
                            start=1,
                        ):
                            st.write(
                                f"**{idx}. {detail['question']}**"
                            )
                            st.write(
                                "Respuesta:",
                                detail.get("user_answer") or "—",
                            )

                            awarded = detail.get("awarded_points")
                            max_points = detail.get("max_points", 1)

                            if awarded is None:
                                st.warning(
                                    f"Pendiente · /{fmt_points(max_points)} pts"
                                )
                            else:
                                st.caption(
                                    f"{fmt_points(awarded)}/"
                                    f"{fmt_points(max_points)} pts"
                                )

                            st.divider()


with tab_publish:
    hero(
        "Publicar QuizForms 🌍",
        "Comprueba si tu app ya está lista para que otras personas entren desde cualquier dispositivo.",
        "ASISTENTE DE PUBLICACIÓN",
    )

    info = sharing_status()
    db_mode = storage_mode()

    c1, c2 = st.columns(2)
    c1.metric(
        "Acceso web",
        "Público ✅" if info["public"] else "Solo local 🏠",
    )
    c2.metric(
        "Base de datos",
        "Supabase ☁️" if db_mode == "supabase" else "SQLite local 💻",
    )

    st.caption("URL detectada")
    st.code(info["base_url"])

    if st.button(
        "🔌 Probar conexión de la base de datos",
        use_container_width=True,
        key="publish_db_healthcheck",
    ):
        ok, message = storage_healthcheck()
        if ok:
            st.success(message)
        else:
            st.error(message)

    if info["public"] and db_mode == "supabase":
        st.success(
            "🎉 Esta instalación está lista para uso real: URL pública + base de datos Supabase."
        )
    elif info["public"] and db_mode != "supabase":
        st.warning(
            "La app ya es pública, pero todavía usa SQLite. Para respuestas de varios compañeros "
            "y mejor persistencia, conecta Supabase antes de usarla en serio."
        )
    elif db_mode == "supabase":
        st.info(
            "Supabase ya está conectado. Solo falta desplegar la app en una URL pública."
        )
    else:
        st.warning(
            "Todavía estás completamente en modo local. Necesitas desplegar la app y conectar Supabase."
        )

    st.subheader("1 · Preparar GitHub")
    with st.container(border=True):
        st.write(
            "Sube **los archivos descomprimidos** de esta versión a un repositorio de GitHub. "
            "El archivo principal es `app.py`."
        )
        st.write("No subas `quizforms.db` ni `.streamlit/secrets.toml`.")
        st.code(
            "app.py\nbackend.py\nparser.py\nrequirements.txt\nsupabase_setup.sql\n.streamlit/config.toml\n.gitignore"
        )

    st.subheader("2 · Conectar Supabase")
    with st.container(border=True):
        st.write(
            "En Supabase crea un proyecto y ejecuta `supabase_setup.sql` en SQL Editor. "
            "Después copia la Project URL y una Secret Key del servidor."
        )

        secrets_example = (
            '[supabase]\n'
            'url = "https://TU-PROYECTO.supabase.co"\n'
            'secret_key = "sb_secret_REEMPLAZAR"\n\n'
            '# Opcional: solo si quieres forzar manualmente la URL pública\n'
            '[app]\n'
            'public_url = "https://TU-APP.streamlit.app"'
        )
        st.code(secrets_example, language="toml")
        st.caption(
            "La Secret Key debe ir en Streamlit Secrets, nunca dentro de app.py ni en un repositorio público."
        )

    st.subheader("3 · Desplegar en Streamlit Community Cloud")
    with st.container(border=True):
        st.write(
            "Crea una app desde tu repositorio de GitHub, usa `app.py` como archivo principal "
            "y pega tus secretos en **Advanced settings → Secrets**."
        )

        p1, p2 = st.columns(2)
        with p1:
            st.link_button(
                "Abrir Streamlit Community Cloud ↗",
                "https://share.streamlit.io",
                use_container_width=True,
            )
        with p2:
            st.link_button(
                "Abrir Supabase ↗",
                "https://supabase.com/dashboard",
                use_container_width=True,
            )

    st.subheader("4 · Comprobación final")
    with st.container(border=True):
        st.write("Cuando vuelvas a abrir esta pestaña en la versión desplegada, deberías ver:")
        st.markdown("- **Acceso web: Público ✅**")
        st.markdown("- **Base de datos: Supabase ☁️**")

        if info["public"]:
            example_code = "ABC123"
            st.write("Ejemplo de enlace que sí puedes compartir:")
            st.code(get_share_link(example_code))
        else:
            st.write(
                "Ahora mismo la app detecta una URL local, así que intencionalmente no marca el sistema como listo."
            )

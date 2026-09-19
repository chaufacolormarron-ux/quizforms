import re


def _clean_lines(text):
    return [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def _split_csv(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def _parse_points(value):
    try:
        points = float(value.replace(",", ".").strip())
        return points if points > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def parse_questions(text):
    lines = _clean_lines(text)
    questions = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.lower().startswith("tipo:"):
            raw_type = line.split(":", 1)[1].strip().lower()
            type_map = {
                "escrita": "written",
                "doctor": "doctor",
                "definición": "definition",
                "definicion": "definition",
                "premisas": "premises",
                "premisa": "premises",
                "tabla": "table",
            }
            qtype = type_map.get(raw_type, "written")

            data = {
                "type": qtype,
                "question": "",
                "options": {},
                "answer": "",
                "keywords": [],
                "points": 1.0,
            }

            if qtype == "premises":
                data["premise_a"] = ""
                data["premise_b"] = ""

            if qtype == "table":
                data["instruction"] = ""
                data["headers"] = []
                data["rows"] = []

            i += 1
            reading_rows = False

            while i < len(lines):
                current = lines[i].strip()
                low = current.lower()

                if not current:
                    i += 1
                    continue

                if low == "fin pregunta":
                    break

                if low.startswith("puntos:"):
                    data["points"] = _parse_points(
                        current.split(":", 1)[1].strip()
                    )
                    i += 1
                    continue

                if qtype == "table" and reading_rows:
                    known_prefixes = (
                        "pregunta:",
                        "respuesta:",
                        "palabras clave:",
                        "instrucción:",
                        "instruccion:",
                        "encabezados:",
                    )
                    if not low.startswith(known_prefixes):
                        data["rows"].append(current)
                        i += 1
                        continue

                if low.startswith("pregunta:"):
                    data["question"] = current.split(":", 1)[1].strip()
                elif low.startswith("respuesta:"):
                    data["answer"] = current.split(":", 1)[1].strip()
                elif low.startswith("palabras clave:"):
                    data["keywords"] = _split_csv(
                        current.split(":", 1)[1].strip()
                    )
                elif qtype == "premises" and (
                    low.startswith("premisa a:") or low.startswith("a:")
                ):
                    data["premise_a"] = current.split(":", 1)[1].strip()
                elif qtype == "premises" and (
                    low.startswith("premisa b:") or low.startswith("b:")
                ):
                    data["premise_b"] = current.split(":", 1)[1].strip()
                elif qtype == "table" and (
                    low.startswith("instrucción:")
                    or low.startswith("instruccion:")
                ):
                    data["instruction"] = current.split(":", 1)[1].strip()
                elif qtype == "table" and low.startswith("encabezados:"):
                    raw = current.split(":", 1)[1].strip()
                    if "|" in raw:
                        data["headers"] = [
                            x.strip() for x in raw.split("|") if x.strip()
                        ]
                    else:
                        data["headers"] = _split_csv(raw)
                elif qtype == "table" and low.startswith("filas:"):
                    after = current.split(":", 1)[1].strip()
                    if after:
                        data["rows"].append(after)
                    reading_rows = True

                i += 1

            if not data["question"]:
                if qtype == "table":
                    data["question"] = (
                        data.get("instruction") or "Completa la tabla"
                    )
                else:
                    data["question"] = f"Pregunta tipo {raw_type}"

            questions.append(data)
            i += 1
            continue

        if line.lower().startswith("palabra:"):
            definition = line.split(":", 1)[1].strip()
            answer = ""
            keywords = []
            points = 1.0
            j = i + 1

            while j < len(lines):
                current = lines[j].strip()
                low = current.lower()

                if not current:
                    j += 1
                    continue
                if low == "fin pregunta":
                    j += 1
                    break
                if low.startswith("respuesta:"):
                    answer = current.split(":", 1)[1].strip()
                elif low.startswith("palabras clave:"):
                    keywords = _split_csv(
                        current.split(":", 1)[1].strip()
                    )
                elif low.startswith("puntos:"):
                    points = _parse_points(
                        current.split(":", 1)[1].strip()
                    )
                elif re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", current):
                    break
                elif low.startswith("tipo:") or low.startswith("palabra:"):
                    break

                j += 1

            questions.append(
                {
                    "type": "definition",
                    "question": definition or "Escribe el término correcto.",
                    "options": {},
                    "answer": answer,
                    "keywords": keywords or ([answer] if answer else []),
                    "points": points,
                }
            )
            i = j
            continue

        match = re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", line)

        if match:
            question_text = match.group(2).strip()
            options = {}
            answer = ""
            keywords = []
            points = 1.0
            j = i + 1

            while j < len(lines):
                current = lines[j].strip()
                low = current.lower()

                if not current:
                    j += 1
                    continue
                if re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", current):
                    break
                if low.startswith("tipo:") or low.startswith("palabra:"):
                    break

                option_match = re.match(
                    r"^\s*([A-Fa-f])[\)\.\-]\s*(.+)$",
                    current,
                )

                if option_match:
                    options[option_match.group(1).upper()] = (
                        option_match.group(2).strip()
                    )
                elif low.startswith("respuesta:"):
                    answer = current.split(":", 1)[1].strip()
                elif low.startswith("palabras clave:"):
                    keywords = _split_csv(
                        current.split(":", 1)[1].strip()
                    )
                elif low.startswith("puntos:"):
                    points = _parse_points(
                        current.split(":", 1)[1].strip()
                    )

                j += 1

            if options:
                questions.append(
                    {
                        "type": "multiple_choice",
                        "question": question_text,
                        "options": options,
                        "answer": answer.upper(),
                        "keywords": [],
                        "points": points,
                    }
                )
            else:
                normalized = answer.casefold()

                if normalized in ["verdadero", "falso"]:
                    questions.append(
                        {
                            "type": "true_false",
                            "question": question_text,
                            "options": {},
                            "answer": (
                                "Verdadero"
                                if normalized == "verdadero"
                                else "Falso"
                            ),
                            "keywords": [],
                            "points": points,
                        }
                    )
                else:
                    questions.append(
                        {
                            "type": "written",
                            "question": question_text,
                            "options": {},
                            "answer": answer,
                            "keywords": keywords,
                            "points": points,
                        }
                    )

            i = j
            continue

        i += 1

    return questions

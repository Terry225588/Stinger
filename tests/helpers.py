from screenmatch.bank import Question, QuestionBank
from screenmatch.normalize import stem_fingerprint


def question(**kwargs) -> Question:
    stem = kwargs["stem"]
    qtype = kwargs.get("qtype", "single")
    labels = {"single": "单选题", "multi": "多选题", "judgment": "判断题"}
    return Question(
        qtype=qtype,
        type_label=kwargs.get("type_label", labels[qtype]),
        stem=stem,
        options=dict(kwargs["options"]),
        answer=kwargs["answer"],
        difficulty=kwargs.get("difficulty", ""),
        basis=kwargs.get("basis", ""),
        analysis=kwargs.get("analysis", ""),
        tag=kwargs.get("tag", ""),
        source_row=kwargs.get("source_row", 2),
        fingerprint=stem_fingerprint(stem),
    )


def bank(*questions: Question) -> QuestionBank:
    return QuestionBank(list(questions), "fixture")

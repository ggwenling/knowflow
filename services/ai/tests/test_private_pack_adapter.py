import importlib.util
from hashlib import sha256
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load(ROOT / "evaluation/adapters/private_pack_to_runner.py")
runner = load(ROOT / "evaluation/runner/runner.py")


def fake_pack(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    pack = tmp_path / "fake-pack"
    pack.mkdir()
    text = "前言\r\n😀合成证据。\r\n"
    documents = []
    for index in range(4):
        raw = text.encode("utf-8")
        name = f"synthetic-{index}.txt"
        (source / name).write_bytes(raw)
        documents.append({"path": name, "sha256": sha256(raw).hexdigest()})
    questions = [{"id": f"fake-{index}", "question": "合成测试问题", "reference_answer": "合成参考",
                  "answerable": index < 15,
                  "evidence": [{"path": documents[index % 4]["path"],
                                "char_start": 4, "char_end": 10, "quote": text[4:10]}]
                  if index < 15 else []} for index in range(20)]
    (pack / "questions.json").write_text(json.dumps({"questions": questions}), encoding="utf-8")
    (pack / "corpus.json").write_text(json.dumps({"documents": documents}), encoding="utf-8")
    freeze(pack)
    return pack, source


def freeze(pack):
    (pack / "COMMITMENT.txt").write_text("\n".join(
        name + " sha256: " + sha256((pack / name).read_bytes()).hexdigest()
        for name in ("questions.json", "corpus.json")), encoding="utf-8")


def test_fake_private_pack_is_accepted_by_runner_with_four_documents(tmp_path, capsys):
    pack, source = fake_pack(tmp_path)
    result = adapter.convert(pack, source)
    manifest, questions, documents, sources, digest = runner._load_dataset(pack / "out/runner")
    assert result == {"questions": 20, "documents": 4, "dataset_sha256": digest}
    assert manifest["synthetic"] is False
    assert manifest["documents"][0]["license"] == "UNSPECIFIED"
    assert len(documents) == len(sources) == 4
    assert sum(q["answerable"] for q in questions) == 15
    assert questions[0]["evidence"][0]["quote"].startswith("😀")
    assert capsys.readouterr().out == ""
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        adapter.convert(pack, source)


@pytest.mark.parametrize("damage", ["hash", "offset", "escape", "duplicate"])
def test_fake_private_pack_rejects_invalid_input_before_output(tmp_path, damage):
    pack, source = fake_pack(tmp_path)
    data = json.loads((pack / "questions.json").read_text(encoding="utf-8"))
    corpus = json.loads((pack / "corpus.json").read_text(encoding="utf-8"))
    if damage == "offset":
        data["questions"][0]["evidence"][0]["char_start"] += 1
    elif damage == "duplicate":
        data["questions"][1]["id"] = data["questions"][0]["id"]
    elif damage == "escape":
        corpus["documents"][0]["path"] = "../escape.txt"
    else:
        corpus["documents"][0]["sha256"] = "0" * 64
    (pack / "questions.json").write_text(json.dumps(data), encoding="utf-8")
    (pack / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    freeze(pack)
    with pytest.raises(ValueError):
        adapter.convert(pack, source)
    assert not (pack / "out").exists()

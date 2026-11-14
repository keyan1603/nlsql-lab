"""Build xiyan_ft_package.zip: the training script, the chat-format data and the README, ready to upload to Kaggle or Colab.

    python train/xiyan_ft/pack.py            # writes train/xiyan_ft/xiyan_ft_package.zip (not committed)

Checks first that no training question is also a test question (nlsql.traindata.LeakFilter over the core, hard, hard2 and decline sets),
so the zip cannot carry a leak even if the data files were edited by hand.
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_training_data import tests_for_leaks    # noqa: E402
from nlsql.traindata import LeakFilter            # noqa: E402

FILES = ["train.jsonl", "val.jsonl", "cont2_train.jsonl", "cont2_val.jsonl"]


def main() -> int:
    leak = LeakFilter(tests_for_leaks())
    bad = 0
    for f in FILES:
        for line in (ROOT / "train" / "data" / f).read_text(encoding="utf-8").splitlines():
            m = json.loads(line)["messages"]
            sql = m[-1]["content"].removeprefix("```sql").removesuffix("```").strip() if m[-1]["content"].startswith("```sql") else None
            if leak.why(m[1]["content"], sql):
                bad += 1
    print("training pairs that overlap a test question:", bad)
    if bad:
        return 1
    out = ROOT / "train" / "xiyan_ft" / "xiyan_ft_package.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "train" / "xiyan_ft" / "train_qlora_7b.py", "train_qlora_7b.py")
        z.write(ROOT / "train" / "xiyan_ft" / "README.md", "README.md")
        for f in FILES:
            z.write(ROOT / "train" / "data" / f, f"data/{f}")
    print("wrote", out, round(out.stat().st_size / 1e6, 1), "MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

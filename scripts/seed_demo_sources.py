from pathlib import Path


def main() -> None:
    root = Path("data/sources")
    root.mkdir(parents=True, exist_ok=True)
    for index in range(1, 31):
        if index % 5 == 0:
            path = root / f"business-{index:02d}.json"
            path.write_text(
                '{"region":"Casablanca-Settat","sector":"automotive","language":"fr"}',
                encoding="utf-8",
            )
        elif index % 3 == 0:
            path = root / f"business-{index:02d}.csv"
            path.write_text(
                "region,sector,language\nTanger-Tetouan,automotive,fr\n", encoding="utf-8"
            )
        elif index % 2 == 0:
            path = root / f"business-{index:02d}.md"
            path.write_text(
                f"# Moroccan business source {index}\n\nAutomotive investment in Morocco.",
                encoding="utf-8",
            )
        else:
            path = root / f"business-{index:02d}.txt"
            path.write_text(f"Source {index}: الاستثمار في المغرب وقطاع الصناعة.", encoding="utf-8")
    print(f"created {len(list(root.iterdir()))} heterogeneous demo documents")


if __name__ == "__main__":
    main()

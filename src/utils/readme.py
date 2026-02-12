"""README conversion helpers."""

from __future__ import annotations

import re

import pandas as pd


def readme_to_csv(file_path: str) -> None:
    """Convert README.md content to expParams CSV."""

    def extract_readme(readme: str) -> dict[str, str]:
        with open(readme, "r", encoding="utf-8") as file:
            readme_content = file.read()

        main_pattern = re.compile(r"##\s(\w+).*?Value:\s([^\n]+)", re.DOTALL)
        sub_pattern = re.compile(r"\*\*(\w+)\*\*.*?Value:\s([^\n]+)", re.DOTALL)

        exp_params: dict[str, str] = {}
        for heading, value in main_pattern.findall(readme_content):
            exp_params[heading.strip()] = value.strip()

        for heading, value in sub_pattern.findall(readme_content):
            exp_params[heading.strip()] = value.strip()

        return exp_params

    exp_params = extract_readme(file_path)
    exp_params = {key: [value] for key, value in exp_params.items()}
    df = pd.DataFrame(exp_params)
    output_file = file_path.replace("README.md", "expParams.csv")
    df.to_csv(output_file, index=False)

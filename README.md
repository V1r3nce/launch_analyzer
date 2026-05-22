# Маппинг требований и тестов в Confluence

Скрипт берёт сьюты Allure TestOps по URL, тянет кейсы, из имени каждого вытаскивает тэг (`O1..O6` / `О1..О6` / `1A..6A` / `1X..6X`) и название требования, по линкам кейса находит фичу (ключ задачи), и обновляет тело страницы Confluence по `--parent_id`.

## Что нужно перед запуском

1. В корне проекта должен быть файл **.env** с переменными (образец — `.env.example`): Allure (URL, токен), Confluence (URL, логин, пароль).
2. Запуск из **корня проекта** и с **PYTHONPATH = корень проекта**, иначе скрипт не найдёт модули.

## Как запустить

**Один сьют:**

```bash
# Windows (PowerShell)
cd C:\Users\...\mapping
$env:PYTHONPATH = (Get-Location).Path
python scripts/confluence/mapping_to_confluence.py --parent_id 860817105 --suite_url "https://allure.nexign.com/project/313/test-cases/836208?treeId=811&from=WzExNTUyN10%3D"
```

```bash
# Linux / macOS
cd /path/to/mapping
export PYTHONPATH=$PWD
python scripts/confluence/mapping_to_confluence.py --parent_id 860817105 --suite_url "https://allure.nexign.com/project/313/test-cases/836208?treeId=811&from=WzExNTUyN10%3D"
```

**Несколько сьютов в одной таблице:**

```bash
python scripts/confluence/mapping_to_confluence.py \
    --parent_id 860817105 \
    --suite_url "URL_сьюта_1" \
    --suite_url "URL_сьюта_2"
```

После успешного запуска тело страницы Confluence заменяется, в браузере ничего нажимать не нужно.
****
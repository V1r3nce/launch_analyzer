"""Обновление страницы маппинга требований и тестов в Confluence."""
from typing import Any, Dict, List

from atlassian import Confluence
from bs4 import BeautifulSoup

from api.exceptions import ConfluencePageNotFoundException
from common.helpers.env_helper import get_var_from_env


class MappingConfluencePage:
    CONFLUENCE_URL = get_var_from_env("CONFLUENCE_URL")
    CONFLUENCE_USERNAME = get_var_from_env("CONFLUENCE_USERNAME")
    CONFLUENCE_PASSWORD = get_var_from_env("CONFLUENCE_PASSWORD")

    HEADERS = [
        "Фича",
        "Ссылка на документацию КР/ГФС",
        "Автор документации",
        "Ссылка на тест-кейсы в Allure",
        "Автор тест-кейсов",
        "Статус",
        "Маппинг требований и тестов",
    ]

    def __init__(self, parent_id: int) -> None:
        self.page_id = int(parent_id)
        self.conf = Confluence(
            url=self.CONFLUENCE_URL,
            username=self.CONFLUENCE_USERNAME,
            password=self.CONFLUENCE_PASSWORD,
        )
        page = self.conf.get_page_by_id(self.page_id, expand="body.storage")
        if not page:
            raise ConfluencePageNotFoundException(
                f"Не нашёл страницу Confluence по id={self.page_id}"
            )
        self.title = page.get("title", "")
        self.body = str(page["body"]["storage"]["value"])
        self.soup = BeautifulSoup(self.body, "html.parser")

    @staticmethod
    def _group_by_feature(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """{feature_key: [rows...]} — все строки одной фичи в одну группу."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            key = (row.get("feature") or {}).get("key") or "—"
            grouped.setdefault(key, []).append(row)
        return grouped

    def build_body(self, mapping_rows: List[Dict[str, Any]]) -> str:
        """Собирает HTML с одной таблицей-маппингом (7 колонок, шапка + строки по фичам)."""
        soup = BeautifulSoup("<div></div>", "html.parser")
        root = soup.div

        table = soup.new_tag("table", **{"class": "wrapped confluenceTable"})
        tbody = soup.new_tag("tbody")

        header_tr = soup.new_tag("tr")
        for col in self.HEADERS:
            th = soup.new_tag("th", **{"class": "confluenceTh"})
            th.string = col
            header_tr.append(th)
        tbody.append(header_tr)

        grouped = self._group_by_feature(mapping_rows)
        for feature_key, rows in grouped.items():
            first = rows[0]
            feature = first.get("feature") or {}
            tr = soup.new_tag("tr")

            # 1. Фича — ссылка на link.url с текстом feature.key.
            td_feature = soup.new_tag("td", **{"class": "confluenceTd"})
            if feature.get("url"):
                a = soup.new_tag("a", href=feature["url"])
                a.string = feature.get("key") or feature.get("name") or "—"
                td_feature.append(a)
            else:
                td_feature.string = feature.get("key", "—")
            tr.append(td_feature)

            # 2. Ссылка на документацию КР/ГФС — все doc_links из первого кейса.
            td_doc = soup.new_tag("td", **{"class": "confluenceTd"})
            for i, link in enumerate(first.get("doc_links") or []):
                if i > 0:
                    td_doc.append(soup.new_tag("br"))
                a = soup.new_tag("a", href=link.get("url", ""))
                a.string = link.get("name") or link.get("url") or ""
                td_doc.append(a)
            tr.append(td_doc)

            # 3. Автор документации — пусто (нет в API кейса).
            tr.append(soup.new_tag("td", **{"class": "confluenceTd"}))

            # 4. Ссылка на тест-кейсы в Allure — исходный --suite_url (не per-case).
            td_suite = soup.new_tag("td", **{"class": "confluenceTd"})
            suite_url = first.get("suite_url", "")
            if suite_url:
                a = soup.new_tag("a", href=suite_url)
                a.string = suite_url
                td_suite.append(a)
            tr.append(td_suite)

            # 5. Автор тест-кейсов — все уникальные owner'ы фичи.
            td_owner = soup.new_tag("td", **{"class": "confluenceTd"})
            owners = sorted({r.get("owner", "") for r in rows if r.get("owner")})
            td_owner.string = ", ".join(owners) if owners else ""
            tr.append(td_owner)

            # 6. Статус — статус кейсов фичи (через запятую, если разные).
            td_status = soup.new_tag("td", **{"class": "confluenceTd"})
            statuses = sorted({r.get("status", "") for r in rows if r.get("status")})
            td_status.string = ", ".join(statuses) if statuses else ""
            tr.append(td_status)

            # 7. Маппинг (вложенная таблица: Тэг | Требование из ГФС | Ссылка на тест-кейс).
            td_mapping = soup.new_tag("td", **{"class": "confluenceTd"})
            inner_table = soup.new_tag("table", **{"class": "wrapped confluenceTable"})
            inner_tbody = soup.new_tag("tbody")
            inner_header_tr = soup.new_tag("tr")
            for inner_col in ("Тэг", "Требование из ГФС", "Ссылка на тест-кейс"):
                th = soup.new_tag("th", **{"class": "confluenceTh"})
                th.string = inner_col
                inner_header_tr.append(th)
            inner_tbody.append(inner_header_tr)

            for row in rows:
                inner_tr = soup.new_tag("tr")

                td_tag = soup.new_tag("td", **{"class": "confluenceTd"})
                td_tag.string = row.get("tag", "")
                inner_tr.append(td_tag)

                td_req = soup.new_tag("td", **{"class": "confluenceTd"})
                td_req.string = row.get("requirement", "—")
                inner_tr.append(td_req)

                td_case = soup.new_tag("td", **{"class": "confluenceTd"})
                tc_url = row.get("test_case_url")
                if tc_url:
                    a = soup.new_tag("a", href=tc_url)
                    a.string = str(row.get("test_case_id", ""))
                    td_case.append(a)
                else:
                    td_case.string = str(row.get("test_case_id", ""))
                inner_tr.append(td_case)
                inner_tbody.append(inner_tr)
            inner_table.append(inner_tbody)
            td_mapping.append(inner_table)
            tr.append(td_mapping)

            tbody.append(tr)

        table.append(tbody)
        root.append(table)
        return str(root)

    def update(self, new_body_html: str) -> Dict[str, Any]:
        """Заменяет тело страницы на new_body_html (заголовок не трогаем)."""
        return self.conf.update_page(
            self.page_id,
            self.title,
            new_body_html,
            always_update=True,
        )

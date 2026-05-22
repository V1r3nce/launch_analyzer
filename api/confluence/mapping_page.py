"""Точечное обновление колонок «Ссылка на тест-кейсы в Allure» и «Маппинг требований и тестов»."""
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from atlassian import Confluence
from bs4 import BeautifulSoup

from api.exceptions import ConfluencePageNotFoundException
from common.helpers.env_helper import get_var_from_env


class MappingConfluencePage:
    CONFLUENCE_URL = get_var_from_env("CONFLUENCE_URL")
    CONFLUENCE_USERNAME = get_var_from_env("CONFLUENCE_USERNAME")
    CONFLUENCE_PASSWORD = get_var_from_env("CONFLUENCE_PASSWORD")

    # Сколько колонок ожидаем в строке (из шапки страницы):
    # Фича | Док КР/ГФС | Автор док | Ссылка на тест-кейсы в Allure | Автор кейсов | Статус | Маппинг
    EXPECTED_COLUMNS = 7
    SUITE_URL_COLUMN_INDEX = 3   # 4-я колонка
    MAPPING_COLUMN_INDEX = -1    # последняя

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

    def build_body(self, mapping_rows: List[Dict[str, Any]]) -> str:
        """
        В существующем теле страницы для каждого --suite_url найти строку
        по ссылке на документацию КР/ГФС (берём из first_case.doc_links[0].url),
        в этой строке:
          • записать suite_url в колонку «Ссылка на тест-кейсы в Allure» (4-я);
          • заменить колонку «Маппинг требований и тестов» (последняя) нашей таблицей
            Тэг | Требование из ГФС | Ссылка на тест-кейс.

        Остальные ячейки и остальные строки не трогаем.
        Если по какому-то suite_url строка не нашлась — кидаем ошибку.
        """
        by_suite: Dict[str, List[Dict[str, Any]]] = {}
        for row in mapping_rows:
            by_suite.setdefault(row.get("suite_url", ""), []).append(row)

        problems: List[str] = []
        for suite_url, rows in by_suite.items():
            doc_urls = self._collect_doc_urls(rows)
            if not doc_urls:
                problems.append(
                    f"{suite_url}: у кейсов нет ссылок на документацию (links[] пустой)"
                )
                continue

            target_a = None
            for doc_url in doc_urls:
                target_a = self._find_anchor_by_url(doc_url)
                if target_a is not None:
                    break
            if target_a is None:
                problems.append(
                    f"{suite_url}: ни одна из {len(doc_urls)} ссылок на страницу не нашлась: "
                    + ", ".join(doc_urls)
                )
                continue
            tr = target_a.find_parent("tr")
            if tr is None:
                problems.append(f"{suite_url}: <a> найден, но не внутри <tr>")
                continue
            tds = tr.find_all("td", recursive=False)
            if len(tds) < self.EXPECTED_COLUMNS:
                problems.append(
                    f"{suite_url}: в найденной строке {len(tds)} td, "
                    f"ожидали {self.EXPECTED_COLUMNS}"
                )
                continue

            self._set_suite_url_cell(tds[self.SUITE_URL_COLUMN_INDEX], suite_url)
            mapping_td = tds[self.MAPPING_COLUMN_INDEX]
            mapping_td.clear()
            mapping_td.append(self._build_inner_mapping_table(rows))

        if problems:
            raise ConfluencePageNotFoundException(
                "Не удалось обновить строки на странице:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )

        return str(self.soup)

    @staticmethod
    def _collect_doc_urls(rows: List[Dict[str, Any]]) -> List[str]:
        """Все непустые URL из links[] всех кейсов группы — без дублей, в исходном порядке."""
        seen: set = set()
        out: List[str] = []
        for r in rows:
            for link in (r.get("doc_links") or []):
                url = (link or {}).get("url") or ""
                if url and url not in seen:
                    seen.add(url)
                    out.append(url)
        return out

    def _find_anchor_by_url(self, target_url: str):
        """
        Ищет <a> с href = target_url. Сравнение умеет в относительные пути:
        href='/pages/viewpage.action?pageId=X' матчится с
        target_url='https://confluence.nexign.com/pages/viewpage.action?pageId=X'.
        """
        target_pq = self._path_with_query(target_url)
        matcher: Callable[[Optional[str]], bool] = lambda href: bool(
            href and (href == target_url or self._path_with_query(href) == target_pq)
        )
        return self.soup.find("a", href=matcher)

    @staticmethod
    def _path_with_query(url: str) -> str:
        parsed = urlparse(url)
        if parsed.query:
            return f"{parsed.path}?{parsed.query}"
        return parsed.path

    def _set_suite_url_cell(self, td, suite_url: str) -> None:
        """Заменяет содержимое td на одну ссылку на suite_url."""
        td.clear()
        a = self.soup.new_tag("a", href=suite_url)
        a.string = suite_url
        td.append(a)

    def _build_inner_mapping_table(self, rows: List[Dict[str, Any]]):
        """Вложенная таблица: Тэг | Требование из ГФС | Ссылка на тест-кейс."""
        soup = self.soup
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
        return inner_table

    def update(self, new_body_html: str) -> Dict[str, Any]:
        """Заменяет тело страницы на new_body_html (заголовок не трогаем)."""
        return self.conf.update_page(
            self.page_id,
            self.title,
            new_body_html,
            always_update=True,
        )

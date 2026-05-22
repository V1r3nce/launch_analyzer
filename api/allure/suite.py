"""Работа со сьютом в Allure TestOps: список кейсов, детали кейсов, сборка маппинга."""
import re
from typing import Any, Dict, List

import requests

from api.allure.name_parser import split_tag_and_requirement
from api.allure.suite_url import SuiteRef, parse_suite_url
from api.exceptions import AllureSuiteNotFoundException, AllureTestCaseNotFoundException
from common.helpers.env_helper import get_var_from_env


_FEATURE_KEY_RE = re.compile(r"^([A-Z]+-\d+)")


def _feature_from_links(links: List[Dict[str, Any]]) -> Dict[str, str]:
    """Первая запись из links[] → {key, name, url}. Ключ парсим из начала name (PROJ-123)."""
    if not links:
        return {"key": "—", "name": "", "url": ""}
    first = links[0]
    raw_name = first.get("name") or ""
    url = first.get("url") or ""
    match = _FEATURE_KEY_RE.match(raw_name)
    key = match.group(1) if match else (raw_name.split(".", 1)[0].strip() or "—")
    return {"key": key, "name": raw_name, "url": url}


def _owner_from_members(members: List[Dict[str, Any]]) -> str:
    """Первый member с role.name == 'Owner'."""
    for m in members or []:
        if (m.get("role") or {}).get("name") == "Owner":
            return m.get("name") or ""
    return ""


class AllureSuite:
    ALLURE_URL = get_var_from_env("ALLURE_URL")
    TOKEN = get_var_from_env("ALLURE_TOKEN")

    def __init__(self, suite_url: str) -> None:
        self.suite_url = suite_url
        self.ref: SuiteRef = parse_suite_url(suite_url)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self._get_jwt_token()}"})

    def _get_jwt_token(self) -> str:
        data = {"grant_type": "apitoken", "scope": "openid", "token": self.TOKEN}
        response = self.session.post(
            self.ALLURE_URL + "/api/uaa/oauth/token", data=data
        )
        assert response.status_code == 200, (
            f"Не удалось авторизоваться в Allure.\n"
            f"Статус: {response.status_code}\nОшибка: {response.text}"
        )
        return response.json().get("access_token")

    def list_test_cases(self) -> List[Dict[str, Any]]:
        """Все кейсы в сьюте через testcasetree/leaf (с пагинацией)."""
        all_cases: List[Dict[str, Any]] = []
        page = 0
        size = 100
        while True:
            url = (
                self.ALLURE_URL
                + "/api/rs/testcasetree/leaf"
                + f"?projectId={self.ref.project_id}"
                + f"&path={self.ref.path}"
                + f"&treeId={self.ref.tree_id}"
                + f"&sort=name%2Casc"
                + f"&size={size}"
                + f"&page={page}"
            )
            response = self.session.get(url)
            assert response.status_code == 200, (
                f"Не удалось получить кейсы сьюта.\n"
                f"URL: {url}\nСтатус: {response.status_code}\nОшибка: {response.text}"
            )
            data = response.json()
            content = data.get("content") or []
            all_cases.extend(content)
            if data.get("last", True) or page + 1 >= data.get("totalPages", 1):
                break
            page += 1
        if not all_cases:
            raise AllureSuiteNotFoundException(
                f"В сьюте {self.suite_url} нет кейсов (или path={self.ref.path} неверный)."
            )
        return all_cases

    def get_test_case_overview(self, test_case_id: int) -> Dict[str, Any]:
        """Полные данные кейса через /api/rs/testcase/{id}/overview."""
        url = self.ALLURE_URL + f"/api/rs/testcase/{test_case_id}/overview"
        response = self.session.get(url)
        if response.status_code == 404:
            raise AllureTestCaseNotFoundException(
                f"Кейс {test_case_id} не найден в Allure."
            )
        assert response.status_code == 200, (
            f"Не удалось получить overview кейса {test_case_id}.\n"
            f"Статус: {response.status_code}\nОшибка: {response.text}"
        )
        return response.json()

    def build_mapping(self) -> List[Dict[str, Any]]:
        """
        Для каждого кейса — {test_case_id, test_case_url, suite_url, tag, requirement,
        feature, status, owner, doc_links}.
        Тэг парсим из имени кейса; поле tags[] из API игнорируем.
        """
        cases = self.list_test_cases()
        result: List[Dict[str, Any]] = []
        for case in cases:
            tc_id = case.get("id")
            if not tc_id:
                continue
            overview = self.get_test_case_overview(tc_id)
            name = overview.get("name") or ""
            tag, requirement = split_tag_and_requirement(name)
            result.append({
                "test_case_id": tc_id,
                "test_case_name": name,
                "test_case_url": (
                    f"{self.ALLURE_URL}/project/{self.ref.project_id}"
                    f"/test-cases/{tc_id}?treeId={self.ref.tree_id}"
                ),
                "suite_url": self.suite_url,
                "tag": tag,
                "requirement": requirement,
                "feature": _feature_from_links(overview.get("links") or []),
                "status": (overview.get("status") or {}).get("name", ""),
                "owner": _owner_from_members(overview.get("members") or []),
                "doc_links": overview.get("links") or [],
            })
        return result

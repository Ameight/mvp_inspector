import os
import requests
from requests.auth import HTTPBasicAuth
from plugins.base_plugin import PluginInterface


class JiraIssueInfoPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "Issue Info"

    def get_description(self) -> str:
        return "Получить информацию по ключу задачи (PROJ-123)."

    def get_category(self) -> str:
        return "Jira"

    def get_required_env(self) -> dict:
        return {
            "JIRA_EMAIL": {
                "label": "Jira Email",
                "description": "Почта аккаунта Jira",
                "secret": False,
            },
            "JIRA_TOKEN": {
                "label": "Jira API Token",
                "description": "Jira → Profile → Security → API tokens",
                "secret": True,
            },
        }

    def get_config_schema(self) -> dict:
        return {
            "issue_key": {
                "label": "Ключ задачи (например PROJ-123)",
                "type": "string",
                "default": "",
            },
        }

    def run(self, inputs: dict) -> str:
        base_url = self.config.get("base_url", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_TOKEN", "")
        issue_key = inputs.get("issue_key", "").strip()

        if not base_url:
            return "❌ Укажи `base_url` в `config.yaml` → `plugins.jira_issue_info`"
        if not email or not token:
            return "❌ Укажи `JIRA_EMAIL` и `JIRA_TOKEN` в `.env`"
        if not issue_key:
            return "❌ Введи ключ задачи"

        url = f"{base_url}/rest/api/3/issue/{issue_key}"
        try:
            r = requests.get(url, auth=HTTPBasicAuth(email, token), timeout=10)
            if r.status_code == 404:
                return f"❌ Задача `{issue_key}` не найдена"
            r.raise_for_status()
        except requests.exceptions.ConnectionError:
            return "❌ Нет подключения к Jira"
        except Exception as e:
            return f"❌ Ошибка: {e}"

        d = r.json()
        fields = d.get("fields", {})
        summary = fields.get("summary", "—")
        status = fields.get("status", {}).get("name", "—")
        assignee = (fields.get("assignee") or {}).get("displayName", "Не назначен")
        priority = (fields.get("priority") or {}).get("name", "—")
        issue_type = (fields.get("issuetype") or {}).get("name", "—")
        desc_text = ""
        desc = fields.get("description")
        if desc and isinstance(desc, dict):
            for block in desc.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        desc_text += inline.get("text", "")
                desc_text += "\n"
        desc_text = desc_text.strip() or "—"

        return (
            f"## [{issue_key}] {summary}\n\n"
            f"| Поле | Значение |\n"
            f"|------|----------|\n"
            f"| Тип | {issue_type} |\n"
            f"| Статус | **{status}** |\n"
            f"| Приоритет | {priority} |\n"
            f"| Исполнитель | {assignee} |\n\n"
            f"### Описание\n\n{desc_text}"
        )

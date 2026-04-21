import os
import requests
from requests.auth import HTTPBasicAuth
from sdk.base_plugin import PluginInterface


class JiraMyTasksPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My Tasks"

    def get_description(self) -> str:
        return "Список открытых задач, назначенных на тебя."

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
            "project": {
                "label": "Проект (оставь пустым — все проекты)",
                "type": "string",
                "default": "",
            },
            "max_results": {
                "label": "Максимум задач",
                "type": "int",
                "default": 20,
            },
        }

    def run(self, inputs: dict) -> str:
        base_url = self.config.get("base_url", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_TOKEN", "")
        project = inputs.get("project", "").strip()
        max_results = int(inputs.get("max_results") or 20)

        if not base_url:
            return "❌ Укажи `base_url` в `config.yaml` → `plugins.jira_my_tasks`"
        if not email or not token:
            return "❌ Укажи `JIRA_EMAIL` и `JIRA_TOKEN` в `.env`"

        jql = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
        if project:
            jql = f"project = {project} AND {jql}"

        url = f"{base_url}/rest/api/3/search"
        try:
            r = requests.get(
                url,
                auth=HTTPBasicAuth(email, token),
                params={"jql": jql, "maxResults": max_results, "fields": "summary,status,priority,issuetype"},
                timeout=10,
            )
            r.raise_for_status()
        except requests.exceptions.ConnectionError:
            return "❌ Нет подключения к Jira"
        except Exception as e:
            return f"❌ Ошибка: {e}"

        issues = r.json().get("issues", [])
        total = r.json().get("total", 0)

        if not issues:
            return "✅ Нет открытых задач"

        rows = ["| Ключ | Тип | Приоритет | Статус | Название |", "|------|-----|-----------|--------|----------|"]
        for issue in issues:
            key = issue.get("key", "—")
            f = issue.get("fields", {})
            summary = f.get("summary", "—")
            status = f.get("status", {}).get("name", "—")
            priority = (f.get("priority") or {}).get("name", "—")
            itype = (f.get("issuetype") or {}).get("name", "—")
            rows.append(f"| `{key}` | {itype} | {priority} | {status} | {summary} |")

        header = f"## Мои задачи ({len(issues)} из {total})\n\n"
        return header + "\n".join(rows)

from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional


class LLMClient:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "langchain_ollama")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.timeout_s = int(os.getenv("LLM_TIMEOUT_S", "8"))
        self.debug = os.getenv("DEBUG_LLM", "0") == "1"
        self._langchain_ready = False
        self._chat_model = None

        if self.provider.startswith("langchain"):
            self._init_langchain()

    def _init_langchain(self) -> None:
        try:
            from langchain_community.chat_models import ChatOllama
        except Exception:
            self._langchain_ready = False
            return

        self._chat_model = ChatOllama(
            model=self.model,
            temperature=0.2,
            timeout=self.timeout_s,
        )
        self._langchain_ready = True

    def chat(self, messages: List[dict]) -> Optional[str]:
        if self._langchain_ready:
            return self._chat_langchain(messages)
        return self._chat_legacy(messages)

    def _chat_langchain(self, messages: List[dict]) -> Optional[str]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return self._chat_legacy(messages)

        if not self._chat_model:
            return self._chat_legacy(messages)

        formatted = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                formatted.append(SystemMessage(content=content))
            else:
                formatted.append(HumanMessage(content=content))

        try:
            response = self._chat_model.invoke(formatted)
            content = getattr(response, "content", None)
            if self.debug:
                print(f"[LLM] response: {content}")
            return content
        except Exception:
            return None

    def _chat_legacy(self, messages: List[dict]) -> Optional[str]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
                body = json.loads(res.read().decode("utf-8"))
                content = body.get("message", {}).get("content", "")
                if self.debug:
                    print(f"[LLM] response: {content}")
                return content
        except Exception:
            return None


__all__ = ["LLMClient"]

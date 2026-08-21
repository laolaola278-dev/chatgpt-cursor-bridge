from .base import AdapterResponse, metadata_response


class DeepSeekAdapter:
    name = "deepseek"
    def chat(self, prompt: str, *, model: str = "deepseek-chat") -> AdapterResponse: return metadata_response(self.name, model, "chat", prompt)
    def analyze(self, prompt: str, *, model: str = "deepseek-chat") -> AdapterResponse: return metadata_response(self.name, model, "analyze", prompt)
    def review(self, prompt: str, *, model: str = "deepseek-chat") -> AdapterResponse: return metadata_response(self.name, model, "review", prompt)

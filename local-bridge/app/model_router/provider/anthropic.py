from .base import AdapterResponse, metadata_response


class AnthropicAdapter:
    name = "anthropic"
    def chat(self, prompt: str, *, model: str = "claude-3-5-sonnet") -> AdapterResponse: return metadata_response(self.name, model, "chat", prompt)
    def analyze(self, prompt: str, *, model: str = "claude-3-5-sonnet") -> AdapterResponse: return metadata_response(self.name, model, "analyze", prompt)
    def review(self, prompt: str, *, model: str = "claude-3-5-sonnet") -> AdapterResponse: return metadata_response(self.name, model, "review", prompt)

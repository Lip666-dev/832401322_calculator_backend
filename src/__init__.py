"""Calculator backend package.

Layers, from the outside in:

``src.server``       HTTP adapter (standard library ``http.server``)
``src.controller``   routing + request validation + response envelopes
``src.service``      use cases (calculate, history, statistics)
``src.model``        SQLite persistence
``src.calculator``   safe expression parsing and evaluation
"""

__all__ = ["config", "errors", "calculator", "validation"]

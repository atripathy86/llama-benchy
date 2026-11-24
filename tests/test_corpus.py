import sys
import types

from llama_benchy.corpus import LightweightTokenizer, TokenizedCorpus


class _FakeEncoding:
    def __init__(self, ids):
        self.ids = ids


class _FakeRawTokenizer:
    def __init__(self):
        self.encode_calls = []
        self.decode_calls = []

    def encode(self, text, add_special_tokens=False):
        self.encode_calls.append((text, add_special_tokens))
        return _FakeEncoding([1, 2, 3])

    def decode(self, token_ids, skip_special_tokens=True):
        self.decode_calls.append((token_ids, skip_special_tokens))
        return "decoded"


def _install_tokenizers(monkeypatch, tokenizer_cls):
    monkeypatch.setitem(
        sys.modules,
        "tokenizers",
        types.SimpleNamespace(Tokenizer=tokenizer_cls),
    )


def _install_transformers(monkeypatch, auto_tokenizer_cls):
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        types.SimpleNamespace(AutoTokenizer=auto_tokenizer_cls),
    )


def test_lightweight_tokenizer_matches_transformers_encode_decode_shape(monkeypatch):
    raw = _FakeRawTokenizer()

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(name, token=None):
            assert name == "repo/model"
            assert token is None
            return raw

    _install_tokenizers(monkeypatch, FakeTokenizer)

    tokenizer = LightweightTokenizer.from_pretrained("repo/model")

    assert tokenizer.encode("hello", add_special_tokens=False) == [1, 2, 3]
    assert tokenizer.decode([1, 2, 3]) == "decoded"
    assert raw.encode_calls == [("hello", False)]
    assert raw.decode_calls == [([1, 2, 3], False)]


def test_get_tokenizer_uses_lightweight_backend_without_transformers(monkeypatch):
    class FakeTokenizer:
        @staticmethod
        def from_pretrained(name, token=None):
            return _FakeRawTokenizer()

    class FakeAutoTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            cls.calls.append((args, kwargs))
            return object()

    _install_tokenizers(monkeypatch, FakeTokenizer)
    _install_transformers(monkeypatch, FakeAutoTokenizer)

    corpus = TokenizedCorpus.__new__(TokenizedCorpus)
    tokenizer = corpus._get_tokenizer("repo/model")

    assert isinstance(tokenizer, LightweightTokenizer)
    assert FakeAutoTokenizer.calls == []


def test_get_tokenizer_lazily_uses_transformers_when_lightweight_fails(monkeypatch):
    class FakeTokenizer:
        @staticmethod
        def from_pretrained(name, token=None):
            raise RuntimeError("missing tokenizer.json")

    class FakeAutoTokenizer:
        calls = []
        tokenizer = object()

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            cls.calls.append((args, kwargs))
            return cls.tokenizer

    _install_tokenizers(monkeypatch, FakeTokenizer)
    _install_transformers(monkeypatch, FakeAutoTokenizer)

    corpus = TokenizedCorpus.__new__(TokenizedCorpus)
    tokenizer = corpus._get_tokenizer("repo/model")

    assert tokenizer is FakeAutoTokenizer.tokenizer
    assert FakeAutoTokenizer.calls == [
        (
            ("repo/model",),
            {
                "use_fast": True,
                "trust_remote_code": False,
                "token": None,
            },
        )
    ]


def test_get_tokenizer_falls_back_to_lightweight_gpt2(monkeypatch):
    class FakeTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, name, token=None):
            cls.calls.append(name)
            if name == "repo/model":
                raise RuntimeError("missing tokenizer.json")
            return _FakeRawTokenizer()

    class FakeAutoTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            cls.calls.append((args, kwargs))
            raise MemoryError("too large")

    _install_tokenizers(monkeypatch, FakeTokenizer)
    _install_transformers(monkeypatch, FakeAutoTokenizer)

    corpus = TokenizedCorpus.__new__(TokenizedCorpus)
    tokenizer = corpus._get_tokenizer("repo/model")

    assert isinstance(tokenizer, LightweightTokenizer)
    assert FakeTokenizer.calls == ["repo/model", "gpt2"]
    assert FakeAutoTokenizer.calls == [
        (
            ("repo/model",),
            {
                "use_fast": True,
                "trust_remote_code": False,
                "token": None,
            },
        )
    ]


def test_get_tokenizer_resolves_quantized_served_model(monkeypatch):
    class FakeTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, name, token=None):
            cls.calls.append(name)
            if name == "GLM-5.3-Flash-EXL3":
                raise RuntimeError("not a Hugging Face repo id")
            return _FakeRawTokenizer()

    class FakeAutoTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            cls.calls.append((args, kwargs))
            raise RuntimeError("not a Hugging Face repo id")

    class FakeHfApi:
        searches = []

        def list_models(self, **kwargs):
            self.searches.append(kwargs)
            return [
                types.SimpleNamespace(id="zai-org/GLM-5.3-Flash"),
                types.SimpleNamespace(id="other/GLM-5.3-Flash-Base"),
            ]

    monkeypatch.setenv("HF_TOKEN", "test-token")
    _install_tokenizers(monkeypatch, FakeTokenizer)
    _install_transformers(monkeypatch, FakeAutoTokenizer)
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(HfApi=FakeHfApi),
    )

    corpus = TokenizedCorpus.__new__(TokenizedCorpus)
    tokenizer = corpus._get_tokenizer("GLM-5.3-Flash-EXL3")

    assert isinstance(tokenizer, LightweightTokenizer)
    assert FakeTokenizer.calls == [
        "GLM-5.3-Flash-EXL3",
        "zai-org/GLM-5.3-Flash",
    ]
    assert FakeAutoTokenizer.calls == [
        (
            ("GLM-5.3-Flash-EXL3",),
            {
                "use_fast": True,
                "trust_remote_code": False,
                "token": "test-token",
            },
        )
    ]
    assert FakeHfApi.searches == [
        {
            "search": "GLM-5.3-Flash",
            "limit": 50,
            "token": "test-token",
        }
    ]


def test_get_tokenizer_does_not_resolve_explicit_tokenizer(monkeypatch):
    class FakeTokenizer:
        calls = []

        @classmethod
        def from_pretrained(cls, name, token=None):
            cls.calls.append(name)
            if name == "chosen/tokenizer":
                raise RuntimeError("missing tokenizer")
            return _FakeRawTokenizer()

    class FakeAutoTokenizer:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise RuntimeError("missing tokenizer")

    class UnexpectedHfApi:
        def __init__(self):
            raise AssertionError("explicit tokenizer should not trigger Hub search")

    _install_tokenizers(monkeypatch, FakeTokenizer)
    _install_transformers(monkeypatch, FakeAutoTokenizer)
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(HfApi=UnexpectedHfApi),
    )

    corpus = TokenizedCorpus.__new__(TokenizedCorpus)
    tokenizer = corpus._get_tokenizer("served-model", "chosen/tokenizer")

    assert isinstance(tokenizer, LightweightTokenizer)
    assert FakeTokenizer.calls == ["chosen/tokenizer", "gpt2"]


def test_tokenizer_stem_only_strips_deployment_suffixes():
    assert (
        TokenizedCorpus._tokenizer_stem("GLM-4.5-Air-AWQ")
        == "GLM-4.5-Air"
    )
    assert (
        TokenizedCorpus._tokenizer_stem("publisher/GLM-4.5-Air-EXL3-8bit")
        == "publisher/GLM-4.5-Air"
    )
    assert TokenizedCorpus._tokenizer_stem("publisher/model") is None

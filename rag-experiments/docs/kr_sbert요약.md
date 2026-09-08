# KR-SBERT 모델 정리

> 출처: https://github.com/snunlp/KR-SBERT  
> 작성일: 2026-06-30

---

## 1. 개요

| 항목 | 내용 |
|------|------|
| 공식 명칭 | KR-SBERT (KoRean SBERT) |
| 개발 기관 | 서울대학교 계산언어학 연구실 (SNUNLP) |
| 기반 논문 | Reimers & Gurevych 2019 (Sentence-BERT) |
| 라이선스 | MIT |
| 최종 업데이트 | 2022년 5월 |

한국어 문장을 **의미 기반 고정 길이 벡터**로 변환하는 모델.  
RAG 파이프라인의 리트리버(Retriever), 문장 유사도 측정, 문서 분류 등에 활용 가능.

---

## 2. SBERT 기본 원리

SBERT는 BERT 위에 **Siamese Network(샴 네트워크)** 구조를 얹어 문장 벡터를 효율적으로 추출한다.

```
문장1 → BERT → Mean Pooling → 벡터 A ─┐
                                        ├→ 코사인 유사도 계산
문장2 → BERT → Mean Pooling → 벡터 B ─┘
```

- 기존 BERT: 두 문장을 쌍(pair)으로 입력 → N개 비교 시 N² 연산 필요
- SBERT: 각 문장을 독립적으로 벡터화 → **O(N)** 연산으로 대용량 유사도 검색 가능

---

## 3. 모델 구조

### 기반 BERT 모델
- `KR-BERT-V40K` 사용 (서울대 자체 개발 한국어 BERT 변형)

### 파인튜닝 데이터셋

| 데이터셋 | 설명 |
|----------|------|
| KLUE-NLI | 한국어 자연어 추론 (Entailment / Neutral / Contradiction) |
| KorSTS (augmented) | 한국어 문장 유사도 데이터 + 데이터 증강 적용 |

### 데이터 증강
- Thakur et al. (2021)의 **in-domain 증강** 방식 적용
- KorSTS 데이터를 확장해 학습 데이터 부족 문제 해결

---

## 4. model.encode 내부 구조

`modules.json`에서 확인한 실제 파이프라인:

```
입력 문장
   ↓
[0_Transformer]  sentence_transformers.models.Transformer
   ↓
[1_Pooling]      sentence_transformers.models.Pooling
   ↓
출력 벡터 (768차원)
```

### 0_Transformer — BERT 설정 (`0_Transformer/config.json`)

| 파라미터 | 값 | 의미 |
|---|---|---|
| `architectures` | `BertModel` | 순수 BERT 인코더 |
| `hidden_size` | 768 | 각 토큰의 벡터 크기 |
| `num_hidden_layers` | 12 | Transformer 블록 수 |
| `num_attention_heads` | 12 | Self-Attention 헤드 수 |
| `max_position_embeddings` | 512 | 최대 토큰 길이 |
| `vocab_size` | 40000 | 모델명 **V40K**의 의미 |

### 1_Pooling — Pooling 설정 (`1_Pooling/config.json`)

```json
{
  "word_embedding_dimension": 768,
  "pooling_mode_cls_token": false,
  "pooling_mode_mean_tokens": true,
  "pooling_mode_max_tokens": false,
  "pooling_mode_mean_sqrt_len_tokens": false
}
```

**Mean Pooling** 방식 사용 — CLS 토큰이 아닌 모든 토큰의 평균으로 문장 벡터 생성:

```
문장: "잠이 옵니다"
     ↓ WordPiece 토크나이저
토큰: [CLS] 잠 ##이 옵 ##니 ##다 [SEP]
     ↓ BERT (12 레이어)
벡터:  v1   v2   v3  v4   v5   v6  v7   ← 각각 768차원
     ↓ Mean Pooling
최종: (v1 + v2 + ... + v7) / 7          ← 768차원 벡터 1개
```

---

## 5. 사용 방법

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')

sentences = ['잠이 옵니다', '졸음이 옵니다', '기차가 옵니다']
vectors = model.encode(sentences)

similarities = util.cos_sim(vectors, vectors)
print(similarities)
# tensor([[1.0000, 0.6577, 0.2732],
#         [0.6577, 1.0000, 0.2730],
#         [0.2732, 0.2730, 1.0000]])
# → '잠이 옵니다'와 '졸음이 옵니다'의 유사도(0.66)가 '기차가 옵니다'(0.27)보다 높음
```

---

## 6. 모델 변형별 성능 비교

문서 분류(Document Classification) 기준:

| 모델명 | Accuracy |
|--------|----------|
| KR-SBERT-Medium-NLI-STS | 0.8400 |
| KR-SBERT-V40K-NLI-STS | 0.8400 |
| KR-SBERT-V40K-NLI-augSTS | 0.8511 |
| **KR-SBERT-V40K-klueNLI-augSTS** | **0.8628** ← 최고 성능 |

---

## 7. 주요 활용 사례

| 용도 | 설명 |
|------|------|
| 문장 유사도(STS) | 두 문장의 의미적 유사도 측정 |
| 패러프레이즈 탐지 | 같은 의미의 다른 표현 문장 찾기 |
| 문서 분류 | 문장 벡터를 피처로 사용한 분류 태스크 |
| RAG 리트리버 | 한국어 문서 의미 기반 검색 |

---

## 8. 설치 및 의존성

```bash
pip install sentence-transformers>=2.2.0
```

HuggingFace Hub 모델 ID: `snunlp/KR-SBERT-V40K-klueNLI-augSTS`

---

## 9. 인용

```bibtex
@misc{kr-sbert,
  author = {Park, Suzi and Hyopil Shin},
  title = {KR-SBERT: A Pre-trained Korean-specific Sentence-BERT model},
  year = {2021},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/snunlp/KR-SBERT}}
}
```

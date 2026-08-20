# Reflection và action plan — Lab 19: GraphRAG vs Flat RAG

**Học viên:** Tống Tiến Mạnh  
**Ngày:** 20/08/2026

## 1. Mapping bài giảng vào implementation

| Khái niệm | Hàm/khối code | Bài học thực tế |
|---|---|---|
| Stream, exact dedup, chunking | `stream_dataset`, `exact_dedup`, `make_chunks` | Giới hạn 1.500 bài/3.000 chunk giúp hoàn thành lab nhưng làm giảm coverage evaluation. |
| Conservative coreference | `resolve_coref_batch`, `run_coref` | Giữ unresolved tốt hơn bịa antecedent; cần audit before/after. |
| Near dedup | `near_dedup_minhash_lsh`, `near_dedup_ann` | Candidate blocking thay O(N²), rồi guard xác nhận để hạn chế false merge. |
| Schema extraction | `extract_triples_batch`, allowlist | Triple phải có evidence, confidence, chunk ID và ngày. |
| Entity resolution | `build_resolution_map`, `merge_guard`, `UF` | Threshold 0.90 ưu tiên precision; audit hiện cần được làm phong phú hơn. |
| Neo4j bulk ingest | `bulk_insert_nodes`, `bulk_insert_edges` | `UNWIND` batch hiệu quả hơn insert từng record; provenance check đạt 0 lỗi. |
| Hybrid retrieval | `retrieve_flat_context`, `retrieve_graph_context` | Graph chỉ hữu ích khi có edge/evidence coverage; thiếu edge thì hybrid cũng thất bại. |
| Evaluation | `judge_answer`, `run_evaluation` | Cần đo retrieval recall trước LLM judge để tách coverage failure khỏi reasoning failure. |

## 2. Điều học được từ debugging

Lỗi khó nhất không phải thuật toán mà là ranh giới giữa các dịch vụ: Groq model/provider có thể thay đổi quyền hoặc khả năng JSON mode; Neo4j Aura có thể đóng socket idle. Cách xử lý hiệu quả là thu lỗi gốc, thực hiện request probe ngắn, retry giới hạn, reconnect driver và không che lỗi bằng một thông báo chung chung.

Benchmark đã cho bài học rõ hơn: score 1/5 không tự động có nghĩa generator kém. Khi context không có gold evidence, cả Flat RAG lẫn GraphRAG đúng ra phải từ chối suy diễn. Vì vậy evaluation production cần có tầng data validation: mỗi question có evidence ID, retrieval recall@k, và trace seed/edge/chunk.

## 3. Kiểm soát AI coding agent

Tôi không chấp nhận hướng pairwise cosine O(N²) cho near-dedup ở quy mô lớn. Quyết định được dựa trên độ phức tạp và chi phí thực tế, không chỉ dựa vào code chạy được trên sample nhỏ. Phương án được chọn là MinHash/LSH hoặc FAISS Top-k để giảm số candidate, sau đó dùng guard và audit để bảo toàn tính giải thích được.

Nguyên tắc sử dụng agent là: yêu cầu agent nêu giả định, đối chiếu với artifact thực tế, giữ provenance, và không đưa số liệu/ca thành công không có evidence vào báo cáo. Các benchmark 1/5 được giữ nguyên thay vì diễn giải thành thành công của GraphRAG.

## 4. Action plan cho đồ án

**Đề xuất bài toán:** trợ lý phân tích tin tức công nghệ và đầu tư. Người dùng có thể hỏi công ty nào đầu tư/mua lại/phát triển sản phẩm gì, hoặc theo dõi thay đổi quan hệ theo thời gian. Flat RAG đủ cho factoid có evidence trong một chunk; Hybrid GraphRAG phù hợp với câu hỏi nối nhiều quan hệ qua bài báo.

Thiết kế graph dự kiến:

- Nodes: `Company`, `Person`, `Technology/Product`, `Investor`, `Event`, `Article`.
- Relations: `FOUNDED`, `LEADS`, `DEVELOPED`, `ACQUIRED`, `INVESTED_IN`, `PARTNERED_WITH`, `USES`, `MENTIONED_IN`.
- Edge metadata: `source_chunk_id`, `article_url`, `published_date`, `evidence`, `confidence`, `extractor_version`.

Chiến lược entity resolution gồm manual aliases cho ticker/doanh nghiệp lớn, ANN candidate theo type, lexical/type guard và human review cho vùng biên. Super-node sẽ dùng cap theo time window, diversity theo source/relation, và temporal expansion có kiểm soát. Mỗi golden question sẽ liên kết với evidence bắt buộc để evaluation đo được cả retrieval coverage lẫn answer quality.

## 5. Tự đánh giá

| Tiêu chí | Điểm (1–5) | Nhận xét |
|---|---:|---|
| Hiểu GraphRAG | 4 | Hiểu pipeline, provenance, traversal và giới hạn coverage. |
| Kiểm soát AI agent | 4 | Ưu tiên kiểm chứng, độ phức tạp và audit thay vì nhận mọi đề xuất. |
| Chất lượng graph hiện tại | 3 | Provenance tốt nhưng graph nhỏ, thiếu audit và super-node thực. |
| Debug/vận hành | 4 | Xử lý Groq/Neo4j và tìm được root cause benchmark. |

Mục tiêu tiếp theo là tăng coverage có kiểm soát, tạo audit entity-resolution đủ 10+ dòng, thêm fixture super-node, và tái chạy benchmark evidence-backed.

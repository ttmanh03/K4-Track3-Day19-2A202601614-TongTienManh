# Thuyết minh kỹ thuật — Lab 19: GraphRAG vs Flat RAG

**Học viên:** Tống Tiến Mạnh  
**Ngày:** 20/08/2026

## 1. Coreference resolution và false edge

Coreference trong cell 1.7 chạy theo batch 5 chunk với nguyên tắc conservative: chỉ thay đại từ/generic reference khi antecedent xuất hiện rõ trong cùng chunk; trường hợp mơ hồ được giữ nguyên và log vào `unresolved_mentions`. Đây là chính sách fail-closed, vì false coreference có thể tạo false edge khó truy vết ở các bước sau.

Ca khó trong dữ liệu HackerNoon là bài **“NaaS Technology Inc. Announces Appointment of Alex Wu as Chief Financial Officer President and Director”**. Mô tả có hai tổ chức: *“The Company is a subsidiary of Newlinks Technology Limited … NaaS provides …”*. Nếu `The Company` bị resolve sang Newlinks thay vì NaaS, một triple như `Company - LEADS -> Alex Wu` sẽ bị gán sai chủ thể. Hậu quả là graph traversal có thể mở rộng từ Newlinks sang các cạnh nhân sự/sự kiện vốn thuộc NaaS.

Biện pháp hiện tại là giữ nguyên mention khi không đủ bằng chứng. Cải tiến bắt buộc cho lần chạy sau là lưu audit gồm `chunk_id`, `original_text`, `resolved_text`, antecedent, confidence và lý do unresolved để kiểm chứng từng quyết định.

## 2. Entity resolution: threshold và guard

`build_resolution_map()` dùng embedding chuẩn hoá, FAISS `IndexFlatIP`, tìm Top-5 láng giềng theo từng entity type và threshold cosine **0.90**. Candidate đạt ngưỡng mới đi qua `merge_guard()`; kết quả được nhóm bằng Union-Find và ghi audit dưới các nhãn `MERGE_MANUAL`, `MERGE_VECTOR` hoặc `REJECT_GUARD_*`.

Ngưỡng 0.90 được chọn theo hướng precision-first. Một alias chưa merge chỉ làm giảm recall; một false merge làm hai thực thể dùng chung canonical ID và làm sai mọi cạnh liên quan. Ticker/manual alias được xử lý trước để các biến thể phổ biến có quy tắc rõ ràng thay vì dựa hoàn toàn vào semantic similarity.

Snapshot hiện tại chưa có candidate audit (`No audit rows` ở cell 5.1), nên không có cặp similarity >0.85 bị guard reject để tuyên bố là kết quả thực nghiệm. Regression test cần bổ sung cặp Company/Product như `Apple`–`Apple Music`, hoặc hai Person cùng họ, xác nhận guard từ chối merge dù embedding gần nhau. Mục tiêu vận hành là xuất tối thiểu 10 audit rows theo rubric.

## 3. Super-node, provenance và graph retrieval

Snapshot Neo4j hiện tại có **95 entity**, **60 cạnh** và **0 cạnh thiếu `source_chunk_id` hoặc `published_date`**. Ba entity có degree cao nhất là:

| Hạng | Entity | Type | Degree |
|---:|---|---|---:|
| 1 | Railergy | Company | 5 |
| 2 | A-Mark Precious Metals | Company | 4 |
| 3 | Apple | Company | 3 |

`retrieve_graph_context()` dùng `SUPER_NODE_DEGREE=100`, `SUPER_NODE_EDGE_CAP=50`, `GLOBAL_EDGE_CAP=250` và `MAX_GRAPH_CONTEXT_CHARS=14000`. Khi degree vượt 100, chỉ tối đa 50 cạnh mới nhất theo `published_date` được đưa vào context. Điều này tránh bùng nổ branching, giảm token/latency và ưu tiên thông tin thời sự.

Đánh đổi là câu hỏi về sự kiện lịch sử có thể cần cạnh cũ đã bị cắt. Cách khắc phục là đọc time range từ query, ưu tiên cạnh trong khoảng thời gian đó và mở rộng temporal window nếu context chưa đủ. Snapshot hiện tại chưa có super-node thực sự (degree lớn nhất 5), vì vậy cần fixture degree >100 để chứng minh assertion cap bằng thực nghiệm.

## 4. Đánh giá Flat RAG và Hybrid GraphRAG

Kết quả từ `outputs/graphrag_eval_results.csv` gồm 5 câu hỏi: 1 factoid, 2 multi-hop và 2 cross-doc.

| Metric trung bình | Flat RAG | GraphRAG | Delta Graph − Flat |
|---|---:|---:|---:|
| Comprehensiveness (1–5) | 1.00 | 1.00 | 0.00 |
| Faithfulness (1–5) | 1.00 | 1.00 | 0.00 |
| Multi-hop reasoning (1–5) | 1.00 | 1.00 | 0.00 |
| Latency (s) | 5.812 | 9.161 | +3.349 |
| Token usage | 2107.8 | 1577.4 | -530.4 |

GraphRAG dùng ít token hơn trong sample nhưng chậm hơn trung bình. Quan trọng hơn, cả hai đạt 1/5 nên không thể kết luận GraphRAG có chất lượng tốt hơn. G04 thiếu evidence về Anthropic/Google/Amazon và G05 thiếu evidence về Microsoft–Azure OpenAI; cả hai hệ thống trả “insufficient evidence”. Nguyên nhân gốc là mismatch giữa golden answer với corpus/index/graph snapshot, không phải reasoning trên bằng chứng đã có.

Quy trình đúng trước LLM judge là gắn `required_chunk_ids` cho mỗi golden question, đo retrieval recall@k và chỉ đánh giá answer quality khi context đã chứa bằng chứng vàng. Sau đó nên thêm một câu kiểm thử có đường đi Neo4j 2-hop đã xác nhận để đo lợi ích của GraphRAG một cách công bằng.

## 5. Trade-off, AI agent control và scale

Flat RAG có indexing/retrieval đơn giản hơn: embedding + FAISS Top-k. Hybrid GraphRAG tăng chi phí vì có coreference, NER/RE, entity resolution, Neo4j ingestion, seed resolution và BFS traversal; đổi lại nó có khả năng nối quan hệ xuyên chunk khi graph có coverage/provenance tốt.

Đề xuất O(N²) pairwise cosine của coding agent bị từ chối cho near-dedup. Với 100.000 bài sẽ có khoảng 5×10⁹ cặp, không phù hợp RAM và thời gian. Pipeline thay bằng MinHash/LSH candidate blocking, hoặc FAISS Top-k ANN, rồi xác nhận bằng Jaccard/lexical guard.

Ở quy mô ~350MB/~100.000 bài, bottleneck đầu tiên là LLM extraction; tiếp theo là entity resolution và Neo4j write throughput. Kiến trúc mở rộng gồm queue worker bất đồng bộ, checkpoint idempotent theo chunk, cache LLM, MinHash/HNSW blocking, batch `UNWIND $rows` 1.000–5.000 records, theo dõi rate limit, và retry/liveness check cho Neo4j Aura.

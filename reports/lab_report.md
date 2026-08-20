# Báo cáo thực hành — Lab 19: GraphRAG vs Flat RAG

**Học viên:** Tống Tiến Mạnh
**Khóa học:** AICB-K34 · Track 3: GraphRAG
**Ngày thực hiện:** 20/08/2026
**Notebook:** `Day19_GraphRAG_vs_FlatRAG_Production_Lab_Guide.ipynb`

## Tóm tắt kết quả

Pipeline đã hoàn tất luồng: stream tập dữ liệu, exact/near dedup, chunking, coreference theo nguyên tắc bảo thủ, trích xuất triple, canonicalization, bulk ingest Neo4j, Flat RAG, Hybrid GraphRAG và đánh giá bằng LLM-as-a-Judge. Snapshot Neo4j cuối cùng có **95 entity**, **60 cạnh** và **0 cạnh thiếu `source_chunk_id` hoặc `published_date`**. Hai artifact benchmark đã được xuất tại `outputs/graphrag_eval_results.csv` và `outputs/graphrag_vs_flatrag_summary.csv`.

Kết quả evaluation hiện tại không chứng minh GraphRAG tốt hơn Flat RAG về chất lượng: cả 5 câu hỏi đều được judge chấm 1/5 trên ba thang điểm. Đây là kết quả quan trọng: pipeline retrieval chưa lấy được bằng chứng tương ứng với golden answers; do đó không được diễn giải các metric hiện tại như bằng chứng về ưu thế chất lượng của GraphRAG.

## 1. Thuyết minh kỹ thuật và phân tích failure mode

### 1.1. Coreference resolution: nguyên tắc bảo thủ và ca khó

Cell 1.7 chạy coreference theo batch 5 chunk, chỉ thay đại từ/generic reference khi antecedent nằm rõ trong cùng chunk. Nếu không chắc, hệ thống giữ nguyên văn bản và ghi `unresolved_mentions`; đây là lựa chọn fail-closed để tránh tạo quan hệ sai trong Knowledge Graph.

Một ca khó lấy trực tiếp từ tập HackerNoon là bài **“NaaS Technology Inc. Announces Appointment of Alex Wu as Chief Financial Officer President and Director”**. Đoạn mô tả chứa hai tổ chức: *“The Company is a subsidiary of Newlinks Technology Limited … NaaS provides …”*. Cụm **“The Company”** có thể chỉ NaaS Technology hoặc bị mô hình nối sai sang Newlinks Technology Limited nếu mất ngữ cảnh câu chủ ngữ. Với một triple như `The Company - LEADS -> Alex Wu`, lỗi này sẽ gán chức danh/quan hệ của NaaS cho Newlinks, từ đó tạo false edge và làm nhiễu traversal nhiều hop.

Quyết định vận hành là không tự động “đoán” trong trường hợp này: giữ `The Company` chưa resolve, log review, rồi chỉ sửa bằng alias/đánh giá thủ công khi có thêm bằng chứng trong chính chunk. Artifact hiện tại không lưu một bảng trước/sau coreference để chứng minh một lần resolve sai cụ thể; đây là khoảng trống audit cần bổ sung ở lần chạy sau: lưu `original_text`, `resolved_text`, antecedent, confidence và lý do giữ nguyên.

### 1.2. Entity resolution: threshold và lexical guard

`build_resolution_map()` dùng cosine similarity **0.90** trên embedding đã chuẩn hoá, FAISS `IndexFlatIP`, và chỉ xét Top-5 láng giềng cùng type. Ticker/manual alias được xử lý trước; sau đó `merge_guard()` quyết định merge hay reject. Các cặp được merge bằng Union-Find để tạo canonical entity, còn quyết định được ghi vào `entity_resolution_audit_df` với `MERGE_MANUAL`, `MERGE_VECTOR` hoặc `REJECT_GUARD_*`.

Tại snapshot hiện có, cell 5.1 in **“No audit rows”**. Vì vậy không có cặp thực nghiệm có similarity >0.85 bị lexical guard chặn để trích dẫn một cách trung thực. Không nên điền một ví dụ giả như `Apple`/`Apple Music` thành kết quả thực nghiệm. Đây là một hạn chế kiểm chứng rõ ràng: đồ thị nhỏ (95 entity) và tập triple hiện chưa sinh candidate vượt threshold.

Ca regression nên thêm cho lần chạy sau là `Apple` (Company) với `Apple Music` (Technology/Product) hoặc hai người cùng họ. Test phải xác nhận similarity cao nhưng type/lexical guard trả `REJECT_GUARD_*`; đồng thời cần xuất ít nhất 10 dòng audit theo rubric. Ngưỡng 0.90 được giữ vì ưu tiên precision hơn recall: false merge làm mất identity và khó khôi phục hơn một alias chưa merge.

### 1.3. Đồ thị, provenance và super-node mitigation

Kiểm tra Neo4j chỉ-đọc cho kết quả:

| Hạng | Entity | Type | Degree |
|---:|---|---|---:|
| 1 | Railergy | Company | 5 |
| 2 | A-Mark Precious Metals | Company | 4 |
| 3 | Apple | Company | 3 |

Truy vấn integrity trả `invalid_provenance_edges = 0`; do đó mọi cạnh hiện có đều giữ `source_chunk_id` và `published_date`.

Chính sách retrieval đặt `SUPER_NODE_DEGREE = 100`, `SUPER_NODE_EDGE_CAP = 50`, `GLOBAL_EDGE_CAP = 250`, `MAX_GRAPH_CONTEXT_CHARS = 14000`. Snapshot hiện tại chưa có super-node: degree cao nhất là 5, nên nhánh cap 50 cạnh chưa được kích hoạt trên dữ liệu thật. Cell 5.1 xác nhận `Railergy` chỉ fetch 5 cạnh. Vì vậy, kết luận đúng là **logic cap đã có nhưng chưa được kiểm chứng bởi super-node thực tế**; cần ingest thêm dữ liệu hoặc tạo fixture >100 cạnh để kiểm thử assertion `len(edges) <= 50`.

Ưu điểm của việc ưu tiên 50 cạnh mới nhất là hạn chế context explosion, giảm latency/token và thường tăng độ phù hợp cho câu hỏi thời sự. Rủi ro là câu hỏi lịch sử có thể mất cạnh cũ quan trọng. Cách giảm rủi ro là nhận diện khoảng thời gian trong query, ưu tiên `published_date` trong khoảng đó, và fallback sang cửa sổ thời gian rộng hơn khi judge/context-completeness báo thiếu bằng chứng.

### 1.4. Benchmark Flat RAG và Hybrid GraphRAG

Kết quả dưới đây được tổng hợp trực tiếp từ `outputs/graphrag_eval_results.csv` (5 câu: 1 factoid, 2 multi-hop, 2 cross-doc).

| Metric trung bình | Flat RAG | GraphRAG | Delta Graph − Flat | Diễn giải |
|---|---:|---:|---:|---|
| Comprehensiveness (1–5) | 1.00 | 1.00 | 0.00 | Cả hai không trả lời được gold answer. |
| Faithfulness (1–5) | 1.00 | 1.00 | 0.00 | Context retrieval không chứa bằng chứng cần thiết. |
| Multi-hop reasoning (1–5) | 1.00 | 1.00 | 0.00 | Không có chuỗi quan hệ đúng để suy luận. |
| Latency (s) | 5.812 | 9.161 | +3.349 | Graph traversal/hybrid context chậm hơn trung bình. |
| Token usage | 2107.8 | 1577.4 | -530.4 | Graph context ngắn hơn ở sample này, nhưng không đủ bằng chứng. |

Theo nhóm câu hỏi, GraphRAG nhanh hơn ở multi-hop (6.119s so với 7.630s) và dùng ít token hơn; ngược lại chậm rõ ở cross-doc (15.661s so với 5.821s). Tuy nhiên, cả hai vẫn có quality score 1.00 nên không thể suy ra hiệu quả chất lượng từ khác biệt cost/latency này.

**Ca lỗi 1 — G04, cả Flat RAG và GraphRAG thất bại.** Câu hỏi: *“What AI product was developed by the organization that received funding from both Google and Amazon?”* Gold answer là **Claude AI**. Cả hai câu trả lời đều nói context không đủ; judge chấm 1/5 ở đủ ba tiêu chí. Nguyên nhân gốc là evidence về Anthropic/Google/Amazon không xuất hiện trong context được retrieve, không phải mô hình suy luận sai một chuỗi có sẵn. Cách khắc phục: tạo golden set từ các chunk đã được index/extract, lưu `required_chunk_ids` cho từng câu, và kiểm tra recall của retrieval trước khi gọi judge.

**Ca lỗi 2 — G05, cả Flat RAG và GraphRAG thất bại.** Câu hỏi yêu cầu mô tả quan hệ Microsoft–Azure OpenAI qua nhiều news chunk; gold answer yêu cầu timeline từ đầu tư đến tích hợp Office 365. Context Flat chỉ có một nhắc chung về Microsoft/AI; Graph context cũng không có cạnh/chunk cần thiết. Lỗi do coverage của corpus/graph extraction và cách thiết kế golden question không khớp snapshot 400 chunk extraction, không phải do super-node cap. Cần truy vết coverage theo từng `reference_answer`, mở rộng extraction cho các chunk bắt buộc và chỉ giữ câu hỏi có evidence truy xuất được.

Không có ca nào trong artifact hiện tại mà Flat RAG thất bại nhưng GraphRAG thành công. Báo cáo không bịa ca này. Sau khi sửa coverage, nên tái chạy benchmark với ít nhất một câu đã xác nhận đường đi 2-hop trong Neo4j (ví dụ `Company - INVESTED_IN -> Organization - DEVELOPED -> Product`) để đo lợi ích kỳ vọng của GraphRAG.

### 1.5. Trade-off, kiểm soát AI agent và scale 350MB

| Khía cạnh | Flat RAG | Hybrid GraphRAG |
|---|---|---|
| Indexing | Chỉ embedding/FAISS; đơn giản và nhanh | Thêm coref, NER/RE, entity resolution, Neo4j ingest; tốn LLM và vận hành hơn |
| Retrieval | Top-k vector chunk; latency thấp hơn | Seed extraction + resolution + traversal + vector fallback; nhiều network round trip |
| Chất lượng kỳ vọng | Tốt với factoid khi evidence nằm trong vài chunk gần nhau | Tốt với multi-hop/cross-document khi graph có coverage và provenance tốt |
| Failure mode chính | Context bị phân mảnh, bỏ sót quan hệ xa | Missing/wrong edge, false merge, super-node, chi phí và lỗi kết nối Neo4j |

AI coding agent từng có thể gợi ý so sánh toàn bộ cặp văn bản bằng cosine similarity O(N²) để near-dedup. Đề xuất này bị từ chối vì với khoảng 100.000 bài sẽ có xấp xỉ 5×10⁹ cặp, không phù hợp RAM/thời gian của bài lab. Thay vào đó pipeline cài MinHash/LSH để tạo candidate và FAISS Top-k để chỉ kiểm tra số láng giềng giới hạn, sau đó dùng Jaccard/lexical guard xác nhận.

Khi mở rộng lên ~350MB/~100.000 bài, bottleneck đầu tiên là LLM extraction theo từng chunk, kế đến là entity resolution và throughput Neo4j. Kiến trúc đề xuất gồm queue worker bất đồng bộ, batch/checkpoint idempotent theo chunk, cache kết quả LLM, candidate blocking MinHash/HNSW, và `UNWIND $rows` 1.000–5.000 bản ghi mỗi batch. Theo dõi thêm retry/rate-limit của LLM và connection lifetime/liveness check của Neo4j Aura.

### 1.6. AI Challenge A — Near deduplication

Near-dedup được hiện thực bằng `near_dedup_minhash_lsh()` với 128 permutation, 32 bands × 4 rows và ngưỡng Jaccard 0.80 trên 2-grams. Cặp ứng viên phải qua `near_dedup_guard()`: ít nhất 20 từ; khi title similarity <0.20 và tỷ lệ độ dài <0.40 thì reject. Bản ANN bổ trợ dùng `all-MiniLM-L6-v2`, FAISS `IndexFlatIP`, Top-5 và threshold 0.88. Candidate/decision được lưu trong `near_dedup_audit_df`; canonical record ưu tiên ngày xuất bản sớm hơn, rồi văn bản dài hơn.

Điểm cần theo dõi là false positive ở boilerplate, press release và tin tài chính template. Các guard structural chỉ giảm rủi ro; vì vậy audit CSV và sampling thủ công vẫn là bắt buộc trước khi áp dụng merge không đảo ngược trên dữ liệu lớn.

## 2. Reflection và action plan

### 2.1. Mapping bài giảng vào code

| Khái niệm | Module/hàm triển khai | Quan sát thực tế |
|---|---|---|
| Streaming, exact dedup, chunking | `stream_dataset`, `exact_dedup`, `make_chunks` | Có giới hạn 1.500 bài, 3.000 chunk để phù hợp thời gian lab. |
| Conservative coreference | `resolve_coref_batch`, `run_coref` | Ưu tiên giữ unresolved hơn tạo false edge; cần lưu audit trước/sau. |
| Near dedup | `near_dedup_minhash_lsh`, `near_dedup_ann` | Dùng candidate blocking thay O(N²), có guard và audit. |
| Schema extraction | `extract_triples_batch`, allowlist node/relation | Triple cần evidence, confidence và provenance. |
| Entity resolution | `build_resolution_map`, `merge_guard`, `UF` | Threshold 0.90; snapshot nhỏ chưa tạo audit candidate. |
| Bulk ingestion | `bulk_insert_nodes`, `bulk_insert_edges` | Neo4j `UNWIND` theo batch; check provenance = 0. |
| Hybrid retrieval | `retrieve_flat_context`, `retrieve_graph_context` | BFS 2-hop, vector context và giới hạn super-node. |
| LLM evaluation | `judge_answer`, `run_evaluation` | CSV đã xuất nhưng exposed retrieval-coverage gap. |

### 2.2. Debugging và bài học

Lỗi khó nhất là tính ổn định khi gọi dịch vụ bên ngoài. Neo4j Aura từng trả `ConnectionResetError (10054)` và không lấy được routing information do socket idle bị server/proxy đóng. Wrapper `run_cypher()` retry các lỗi `ServiceUnavailable`, `SessionExpired`, `TransientError`, đóng driver cũ và reconnect; sau retry cell 5.1 vẫn trả được Railergy degree 5. Bài học là không coi một kết nối TCP đã tạo là luôn sống; cần liveness check, connection lifetime hợp lý và retry idempotent.

Một failure mode khác là model Groq cũ/không còn được cấp quyền. Danh sách model không đủ để đảm bảo endpoint chat hoặc JSON mode hoạt động trong mọi cấu hình. Cách debug là thử một request ngắn cho từng model/provider, tách model generation và judge, và hiển thị lỗi gốc thay vì bọc mọi lỗi thành “không có quyền”.

Bài học quan trọng nhất từ benchmark là phải kiểm tra data coverage trước quality. Golden answer đúng nhưng không có chunk/evidence tương ứng trong corpus index hoặc graph thì Flat RAG lẫn GraphRAG đều chỉ có thể trả lời “insufficient evidence”. Lần chạy kế tiếp sẽ gắn mỗi câu gold với `required_chunk_ids`, đo retrieval recall@k và chỉ đánh giá answer quality khi evidence coverage đạt yêu cầu.

### 2.3. Action plan áp dụng thực tế

**Đề xuất đồ án:** trợ lý phân tích tin tức công nghệ và đầu tư. Đây là bài toán phù hợp Hybrid GraphRAG vì người dùng thường hỏi quan hệ giữa công ty, sản phẩm, nhà sáng lập, khoản đầu tư và mốc thời gian qua nhiều bài viết; câu hỏi tra cứu đơn giản vẫn nên đi qua Flat RAG để giảm latency.

Thiết kế sơ bộ:

- Nodes: `Company`, `Person`, `Technology/Product`, `Investor`, `Event`, `Article`.
- Relations: `FOUNDED`, `LEADS`, `DEVELOPED`, `ACQUIRED`, `INVESTED_IN`, `PARTNERED_WITH`, `USES`, `MENTIONED_IN`.
- Thuộc tính bắt buộc của edge: `source_chunk_id`, `article_url`, `published_date`, `evidence`, `confidence`, `extractor_version`.

Entity resolution sẽ dùng manual alias cho doanh nghiệp lớn/ticker, vector candidate theo type, lexical/type guard và hàng đợi human review cho candidate biên. Super-node sẽ áp dụng cap theo thời gian, diversity sampling theo relation/source và temporal query expansion thay vì chỉ lấy 50 cạnh mới nhất. Evaluation sẽ được thiết kế evidence-backed: mỗi golden question có gold answer, quan hệ/chunk bắt buộc và một test retrieval coverage trước LLM judge.

## 3. Tự đánh giá và checklist

| Tiêu chí | Điểm tự chấm (1–5) | Ghi chú |
|---|---:|---|
| Hiểu GraphRAG | 4 | Nắm được pipeline, provenance, graph traversal và giới hạn coverage. |
| Kiểm soát AI coding agent | 4 | Từ chối O(N²), kiểm tra artifact và không suy diễn từ output thiếu chứng cứ. |
| Chất lượng đồ thị hiện tại | 3 | Provenance đạt 0 lỗi, nhưng đồ thị nhỏ và chưa có audit/entity/super-node đủ mạnh. |
| Debug và vận hành | 4 | Xử lý retry Neo4j/Groq và xác định root cause benchmark. |

Checklist trước khi nộp:

- [x] Neo4j schema và bulk `UNWIND` đã chạy.
- [x] 0 edge thiếu `source_chunk_id` hoặc `published_date`.
- [x] Đã xuất `outputs/graphrag_eval_results.csv` và `outputs/graphrag_vs_flatrag_summary.csv`.
- [x] Đã ghi nhận metric benchmark và failure analysis trung thực.
- [ ] Tái chạy entity resolution để có ít nhất 10 audit rows theo rubric.
- [ ] Bổ sung/điều chỉnh golden set theo evidence có trong corpus và tái đánh giá.
- [ ] Kiểm thử super-node bằng dữ liệu/fixture degree >100.

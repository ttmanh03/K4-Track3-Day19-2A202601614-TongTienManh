# Failure analysis — Lab 19: GraphRAG vs Flat RAG

**Học viên:** Tống Tiến Mạnh  
**Ngày:** 20/08/2026

## Bằng chứng sử dụng

Phân tích dựa trên `outputs/graphrag_eval_results.csv`, `outputs/graphrag_vs_flatrag_summary.csv` và output đã lưu của notebook. Snapshot graph gồm 95 entity, 60 cạnh, không có cạnh thiếu provenance.

## Ca 1 — Golden question G04 không có evidence được retrieve

**Câu hỏi:** “What AI product was developed by the organization that received funding from both Google and Amazon?”  
**Gold answer:** Claude AI.  
**Kết quả:** Flat RAG và GraphRAG đều nhận 1/5 cho comprehensiveness, faithfulness và multi-hop reasoning.

### Triệu chứng

Cả hai câu trả lời nói context không đủ. Judge nêu rõ answer không nhắc Anthropic/Claude AI và không giải quyết quan hệ funding Google–Amazon.

### Root cause

Đây không phải lỗi suy luận trên evidence sẵn có. Context retrieved không chứa các chunk/cạnh về Anthropic, Google, Amazon và Claude. Graph chỉ có 60 cạnh do extraction giới hạn; golden question lại đòi một chuỗi quan hệ không được chứng minh trong snapshot đó.

### Cách khắc phục

1. Lập golden set từ chính corpus đã index/extract, không chỉ từ tri thức kỳ vọng.
2. Lưu `required_chunk_ids` và `required_relation_path` cho mỗi gold question.
3. Thêm preflight retrieval recall@k: nếu evidence không được retrieve thì đánh dấu benchmark invalid/coverage failure, không chấm answer quality.
4. Mở rộng extraction cho các chunk chứa evidence bắt buộc, rồi xác minh đường đi `Investor -> INVESTED_IN -> Organization -> DEVELOPED -> Product` trong Neo4j.

## Ca 2 — Golden question G05 thiếu coverage cross-document

**Câu hỏi:** xác định công nghệ gắn với cùng một công ty trong ít nhất hai news chunk và mô tả thay đổi theo thời gian.  
**Gold answer:** Microsoft và Azure OpenAI services, từ đầu tư đến tích hợp Office 365.  
**Kết quả:** Flat RAG và GraphRAG đều nhận 1/5 trên ba thang điểm.

### Triệu chứng

Flat context chỉ có một nhắc chung về Microsoft/AI. Graph context cũng không có hai chunk/cạnh chứng minh timeline. Hai generator đều trả lời thiếu evidence.

### Root cause

Câu hỏi yêu cầu cross-document temporal evidence trong khi extraction snapshot không chứa đủ edge có provenance tương ứng. Đây là coverage mismatch, không phải super-node cap: degree cao nhất chỉ là 5, thấp hơn nhiều so với threshold 100.

### Cách khắc phục

1. Với câu cross-document, yêu cầu ít nhất hai distinct `source_chunk_id` trước khi cho generator trả lời.
2. In retrieval debug cho seed entity, matched node, edge list và source chunk list.
3. Nếu chỉ có một source, trả về trạng thái `INSUFFICIENT_RETRIEVAL_COVERAGE` thay vì để LLM diễn giải thiếu evidence.
4. Thiết kế câu đánh giá sau khi đã kiểm tra evidence coverage và timeline relation trong Neo4j.

## Ca 3 — Neo4j Aura reset connection giữa các cell

### Triệu chứng

Cell 5.1 từng in `ConnectionResetError (10054)` và `Unable to retrieve routing information`, sau đó retry thành công và trả `Railergy`, degree 5, fetched 5. Không có exception cuối cùng.

### Root cause

Socket trong connection pool bị Aura hoặc proxy đóng khi idle. Khi driver tái sử dụng socket defunct, routing/read thất bại. Đây là lỗi hạ tầng tạm thời, không phải Cypher/schema sai.

### Cách khắc phục

`run_cypher()` retry các lỗi `ServiceUnavailable`, `SessionExpired`, `TransientError` và `OSError`, đóng driver cũ rồi reconnect. Cấu hình nên giữ `liveness_check_timeout`, `keep_alive`, `max_connection_lifetime` hữu hạn, `connection_acquisition_timeout`, và chỉ retry thao tác idempotent. Nếu retry cạn, thông báo phải chỉ rõ kiểm tra trạng thái AuraDB, URI/database và firewall port 7687.

## Kết luận vận hành

Hai failure case benchmark cho thấy trước khi tối ưu prompt/model phải kiểm tra evidence coverage. Failure hạ tầng cho thấy external services cần health check và retry. Các kiểm thử còn thiếu là: entity-resolution audit >=10 rows và super-node fixture degree >100 để xác minh cap 50 cạnh.

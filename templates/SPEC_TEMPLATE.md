# Technical Specification: [Feature Name]

> Template dành cho phần Requirement Analysis & Spec Writing.

## 1. Overview & Objective
- **Feature Summary**: Mô tả ngắn gọn tính năng làm gì.
- **Problem Statement**: Vấn đề mà tính năng này giải quyết.
- **Target Audience / Roles**: Ai là người sử dụng (Owner, Collaborator/Guest, Admin...).

## 2. User Stories & Acceptance Criteria
### User Story 1: [Tiêu đề US 1]
- **As a** [role]
- **I want to** [action]
- **So that** [benefit]
- **Acceptance Criteria**:
  - [ ] Tiêu chí 1
  - [ ] Tiêu chí 2

### User Story 2: [Tiêu đề US 2]
- **As a** [role]
- **I want to** [action]
- **So that** [benefit]
- **Acceptance Criteria**:
  - [ ] Tiêu chí 1

## 3. Scope
- **In-Scope**: Các chức năng bắt buộc phải có trong phiên bản này.
- **Out-of-Scope**: Những chức năng cố tình loại bỏ / để dành phiên bản sau để tránh scope creep.

## 4. Database Design
- **New Tables / Altered Tables**:
  - Tên bảng, kiểu dữ liệu các cột, Primary Key, Foreign Key.
- **Constraints & Indexes**:
  - Unique constraints, foreign keys on delete behavior.
  - Các index cần đánh để tối ưu truy vấn.

## 5. API Contracts & Endpoints
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| POST | `/api/v1/...` | ... | Yes |
| GET | `/api/v1/...` | ... | Yes |

- **Request Body & Validation Schema** (Pydantic / JSON format).
- **Responses & Error Codes** (200, 201, 400, 403, 404, 422).

## 6. Business Logic & Security Considerations
- **Authorization & Permission Matrix**:
  - Ai được đọc, ai được sửa, ai được xoá?
  - Xử lý thế nào nếu người được share tự chia sẻ tiếp?
- **Edge Cases & Race Conditions**:
  - Mời trùng lặp?
  - Owner thu hồi quyền trong lúc collaborator đang gửi request sửa?
  - User tự share cho chính mình?

## 7. Caching & Invalidation Strategy
- Cấu trúc Redis cache key khi áp dụng quyền truy cập.
- Khi nào cần invalidate cache (Owner update, Collaborator update, Owner revoke quyền).

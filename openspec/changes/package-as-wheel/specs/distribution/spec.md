# Spec Delta

## Purpose

Cho phép cài đặt `unit-test-designer` bằng một lệnh `pip install` trên mọi máy có Python, với wheel tự chứa toàn bộ dữ liệu rule và tài liệu skill, kèm lệnh riêng để cài phần skill vào thư mục cấu hình Claude Code, và quy trình CI/release tự động hoá việc kiểm chứng và phát hành.

## ADDED Requirements

### Requirement: Wheel tự chứa toàn bộ dữ liệu runtime

Package SHALL chứa `rules/`, `data/`, và tài liệu skill bên trong thư mục package (`utd/_data/`), để cài bằng `pip install` là đủ và không phụ thuộc thư mục bên ngoài. Mã nguồn MUST NOT dùng đường dẫn tương đối vượt ra ngoài package để đọc dữ liệu.

#### Scenario: Cài trong venv sạch
- **WHEN** cài wheel vào một venv mới và chạy `utd inventory` trên fixture có sẵn
- **THEN** lệnh đọc được 150 rule và in `reachability: 150/150 OK` mà không cần biến môi trường nào

#### Scenario: Không còn đường dẫn vượt package
- **WHEN** tìm trong `utd/` các biểu thức `parent.parent.parent`
- **THEN** không còn kết quả nào dùng để đọc `rules/` hoặc `data/`

### Requirement: Đọc dữ liệu qua importlib.resources

Mọi truy cập dữ liệu runtime SHALL dùng `importlib.resources.files("utd")` làm gốc, không dùng `Path(__file__)`. Việc sắp xếp danh sách file MUST dùng khoá tường minh (`key=lambda p: p.name`) vì `Traversable` không định nghĩa thứ tự so sánh.

#### Scenario: Sắp xếp file rule không ném lỗi
- **WHEN** `load_rules()` duyệt thư mục rule và sắp xếp kết quả
- **THEN** không ném `TypeError` trên Python 3.10, 3.11, và 3.12

#### Scenario: Ba hằng số trỏ đúng chỗ
- **WHEN** kiểm tra `DEFAULT_RULES_DIR`, `DEFAULT_DATA_DIR`, `DEFAULT_TIERS_PATH`
- **THEN** cả ba là `Traversable` trỏ vào `utd/_data/` và đọc được file tương ứng

### Requirement: Cài skill bằng lệnh riêng

`utd install-skill` SHALL copy toàn bộ tài liệu skill từ wheel vào thư mục đích (mặc định `~/.claude/skills/unit-test-designer`), kiểm `SKILL.md` có frontmatter `name` và `allowed-tools` trước khi ghi, và MUST NOT tự chạy trong lúc `pip install`.

#### Scenario: Cài skill lần đầu
- **WHEN** chạy `utd install-skill` khi thư mục đích chưa tồn tại
- **THEN** lệnh tạo thư mục, copy `SKILL.md`, `SCHEMA.md`, `references/`, `assets/`, và in đường dẫn đã cài kèm nhắc mở phiên mới

#### Scenario: Không ghi đè khi thiếu --force
- **WHEN** thư mục đích đã tồn tại và chạy `utd install-skill` không có `--force`
- **THEN** lệnh thoát với exit 1, in đường dẫn hiện có, và không ghi file nào

#### Scenario: Kiểm frontmatter trước khi copy
- **WHEN** `SKILL.md` nguồn thiếu `allowed-tools`
- **THEN** lệnh từ chối cài và nêu trường còn thiếu

#### Scenario: Chạy thử không ghi
- **WHEN** chạy `utd install-skill --dry-run`
- **THEN** lệnh liệt kê file sẽ ghi và không tạo file nào

### Requirement: Metadata gói đầy đủ

`pyproject.toml` SHALL khai `requires-python >= 3.10`, dependency `openpyxl>=3.1`, extra `yaml` cho `pyyaml>=6`, entry point `utd = "utd.cli:main"`, và `package-data` bao phủ toàn bộ `utd/_data/**`.

#### Scenario: Wheel chứa dữ liệu
- **WHEN** build wheel và liệt kê nội dung file `.whl`
- **THEN** có ít nhất 10 file `utd/_data/rules/*.json`, 3 file `utd/_data/data/*.json`, và `utd/_data/skill/SKILL.md`

#### Scenario: Entry point tạo lệnh utd
- **WHEN** cài wheel rồi chạy `utd --version`
- **THEN** in `utd 2.0.0` và thoát 0

### Requirement: CI kiểm chứng trên nhiều phiên bản

Workflow CI SHALL chạy test trên matrix Python 3.10/3.11/3.12 và hai hệ điều hành ubuntu/windows, và MUST có một bước xác nhận wheel chứa `_data` trước khi coi build là thành công.

#### Scenario: CI đỏ khi thiếu package-data
- **WHEN** `package-data` khai thiếu một glob khiến wheel không chứa `_data/rules/*.json`
- **THEN** bước kiểm tra wheel trong CI thất bại và job build báo đỏ

#### Scenario: Test chạy trên cả Windows
- **WHEN** CI chạy trên `windows-latest` với Python 3.12
- **THEN** toàn bộ test pass, bao gồm test in tiếng Việt trên console mặc định

### Requirement: Phát hành khi tạo tag

Workflow release SHALL build wheel và tạo GitHub Release đính kèm file `.whl` khi một tag khớp `v*` được push. Lệnh release MUST NOT chạy trên push thường.

#### Scenario: Tag tạo release
- **WHEN** push tag `v2.0.0`
- **THEN** workflow build wheel và tạo Release `v2.0.0` đính kèm file `unit_test_designer-2.0.0-py3-none-any.whl`

#### Scenario: Push thường không tạo release
- **WHEN** push commit lên nhánh master không có tag
- **THEN** workflow release không chạy

### Requirement: Repository công khai có cấu trúc và giấy phép

Repo `h004888/unit-test-designer` SHALL ở mức PUBLIC, chứa `LICENSE` MIT, `README.md` mô tả cài đặt và 8 lệnh, `.gitignore` loại trừ artefact, và lịch sử git MUST NOT chứa skill của công cụ khác.

#### Scenario: Clone rồi cài được
- **WHEN** clone repo và chạy `pip install .`
- **THEN** cài thành công, `utd --version` chạy được, và `utd install-skill` cài được skill

#### Scenario: History không chứa skill ngoài
- **WHEN** kiểm tra toàn bộ lịch sử git của repo
- **THEN** không có đường dẫn nào dưới `.claude/skills/` hay `.agents/skills/`

#### Scenario: README đủ thông tin cài đặt
- **WHEN** đọc `README.md`
- **THEN** có hướng dẫn cài từ wheel/release, danh sách 8 lệnh, và cách gỡ

# Token kapsamları

Her makine/rol için ayrı fine-grained token:
- Contents: Read and write (yalnız ilgili repo)
- Metadata: Read-only
- Pull requests: Read and write (geliştirici + karar)
- Commit statuses: Read-only
- Issues: Read-only (PR yorumları için)
Dosya 0600; repo dışında; kapı token'ı ajanlara verilmez.

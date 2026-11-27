// Package ledger is what the companion remembers between runs, and the only
// package that reads or writes it (docs/design/library.md, 4.6.1):
//
//   - fetched.json (Fetched): the server tracks this computer fetched, by
//     audio id, and the tombstones it handled;
//   - state.json (Synced): the local files a sync has handled, and the
//     tracks it listed in the "removed on server" playlist.
//
// A read that leads to a write happens under the file's lock (FetchLock,
// SyncLock), the only way to save either file. A read for a question only
// may be a snapshot (ReadFetched, ReadSynced): files are replaced by a
// rename, so a snapshot is always whole. The formats and their migrations
// are the ones the companion has always written; older companions read
// everything this package writes.
package ledger

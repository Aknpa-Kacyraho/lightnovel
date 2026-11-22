package com.kacyraho.lightnovel.core.util

import android.content.ContentResolver
import android.net.Uri

/**
 * Removes a document previously created with `CreateDocument`.
 *
 * Export failures must not leave a half-written zip/epub behind. The URI is
 * always a freshly created document, never a file the user already owned, so
 * deleting it on failure is safe. Some providers reject deletion; that must
 * not mask the original export error.
 */
fun discardCreatedDocument(uri: Uri, resolver: ContentResolver) {
    runCatching { resolver.delete(uri, null, null) }
}

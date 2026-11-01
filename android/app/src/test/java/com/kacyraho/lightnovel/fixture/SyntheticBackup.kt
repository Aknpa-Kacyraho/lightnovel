package com.kacyraho.lightnovel.fixture

import com.kacyraho.lightnovel.data.backup.BackupManifest
import java.nio.file.Path

object SyntheticBackup {
    fun nineteenBooks(path: Path): BackupManifest {
        val fx = ZipFixture()
        val items = StringBuilder()
        var first = true

        for (i in 1..19) {
            val id = "kakuyomu-$i"
            val dir = when (i) {
                3 -> "short-3"
                4 -> "orphan-4-日本語"
                else -> id
            }
            val title = "Synthetic Book $i"
            if (i != 4) {
                if (!first) items.append(',')
                first = false
                val slug = if (i == 3) "\"short-3\"" else "\"$id\""
                val shelf = if (i == 1 || i % 3 == 0) "reading" else "want"
                val favorite = i == 1
                val added = "\"2026-10-01T00:00:00\""
                items.append(
                    "\"$id\":{\"id\":\"$id\",\"slug\":$slug,\"source\":\"kakuyomu\"," +
                        "\"source_id\":\"$i\",\"title\":\"$title\",\"shelf\":\"$shelf\"," +
                        "\"favorite\":$favorite,\"hidden\":false,\"added_at\":$added}",
                )
            }
            fx.add("novels/$dir/meta.json", "{\"title\":\"$title\",\"episodes\":1}")
            fx.add("novels/$dir/raw/0001.txt", "日本語の本文 $i")
            fx.add("novels/$dir/chapters/0001.txt", "中文译文 $i")
            fx.add("novels/$dir/chapters/0001.meta.json", "{\"complete\":true}")
        }

        if (!first) items.append(',')
        items.append(
            "\"kakuyomu-20\":{\"id\":\"kakuyomu-20\",\"slug\":\"kakuyomu-20\"," +
                "\"source\":\"kakuyomu\",\"source_id\":\"20\",\"title\":\"Missing Dir\"," +
                "\"shelf\":\"reading\",\"favorite\":false,\"hidden\":false}",
        )
        fx.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{$items},\"candidates\":{}," +
                "\"aliases\":{\"old-1\":\"kakuyomu-1\",\"chain-a\":\"chain-b\"," +
                "\"chain-b\":\"kakuyomu-2\"}}",
        )
        fx.add("data/slug-aliases.json", "{\"side-1\":\"kakuyomu-1\"}")
        fx.add("data/books/kakuyomu-1.json", "{\"tracking\":\"reading\",\"favorites\":true}")
        fx.add(
            "data/books/kakuyomu-2.json",
            "{\"tracking\":\"finished\",\"favorites\":false,\"progress\":{\"chapter\":5}," +
                "\"opened\":\"2026-10-01 10:00:00\",\"finished\":\"2026-10-02 10:00:00\"}",
        )
        fx.add("data/jobs/quarantine/bad.json", "not-json")
        fx.add("lnfinder/taste_profile.json", "{}")

        val manifest = fx.manifest()
        fx.write(path, manifest)
        return manifest
    }

    fun conflictedSlugs(path: Path): BackupManifest {
        val fx = ZipFixture()
        fx.add("novels/kakuyomu-1/meta.json", "{\"title\":\"A\"}")
        fx.add("novels/kakuyomu-2/meta.json", "{\"title\":\"B\"}")
        fx.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{" +
                "\"kakuyomu-1\":{\"id\":\"kakuyomu-1\",\"slug\":\"same\",\"title\":\"A\"}," +
                "\"kakuyomu-2\":{\"id\":\"kakuyomu-2\",\"slug\":\"same\",\"title\":\"B\"}" +
                "},\"candidates\":{},\"aliases\":{}}",
        )
        val manifest = fx.manifest()
        fx.write(path, manifest)
        return manifest
    }
}

package com.kacyraho.lightnovel.reader

object SampleText {
    val long: String = (1..40).joinToString("\n\n") { i ->
        "第${i}段：これはページ分割のサンプルです。中文和日文混排，用来检查分页是否覆盖完整、" +
            "翻页是否跟手。这里没有引用任何真实作品，只是生成的演示文本。" +
            "「ページをめくる感触を確認します」と彼女は言った。"
    }
}

package com.kacyraho.lightnovel.feature.reader

/**
 * 阅读页横幅只承载「正在发生」或「需要处理」的状态。
 * 单纯的「本章还没翻译」不再常驻，避免每章顶部挂一块静态提示。
 */
internal fun shouldShowTranslationBanner(
    status: TranslationStatus,
    hasTranslation: Boolean,
    running: Boolean,
    hasTask: Boolean,
    hasError: Boolean,
    hasMessage: Boolean,
    queueActive: Boolean,
    queuePaused: Boolean,
    queueError: Boolean,
): Boolean {
    if (running || hasTask || hasError || hasMessage) return true
    if (queueActive || queuePaused || queueError) return true
    if (status == TranslationStatus.FAILED) return true
    if (!hasTranslation) return false
    return status == TranslationStatus.QUEUED ||
        status == TranslationStatus.TRANSLATING ||
        status == TranslationStatus.STALE
}

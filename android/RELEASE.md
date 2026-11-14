# Android Release 构建

正式 APK 不提交签名私钥，也不把密码写入 `gradle.properties`。Gradle 只从环境变量读取四项签名信息：

| 环境变量 | 内容 |
| --- | --- |
| `LIGHTNOVEL_RELEASE_STORE_FILE` | keystore 绝对路径，放在仓库外 |
| `LIGHTNOVEL_RELEASE_STORE_PASSWORD` | keystore 密码 |
| `LIGHTNOVEL_RELEASE_KEY_ALIAS` | key alias |
| `LIGHTNOVEL_RELEASE_KEY_PASSWORD` | key 密码 |

四项必须同时存在。缺任意一项，`assembleRelease` 会明确失败，避免悄悄生成未签名 APK。

## 首次创建 keystore

```powershell
keytool -genkeypair -v `
  -keystore "$env:USERPROFILE\lightnovel-release.jks" `
  -alias lightnovel `
  -keyalg RSA -keysize 4096 -validity 10000
```

密码由你自己输入并安全保存。不要把 `.jks` 放进仓库、网盘公开目录或聊天附件。

## 构建

```powershell
$env:LIGHTNOVEL_RELEASE_STORE_FILE="$env:USERPROFILE\lightnovel-release.jks"
$env:LIGHTNOVEL_RELEASE_STORE_PASSWORD="<你的 keystore 密码>"
$env:LIGHTNOVEL_RELEASE_KEY_ALIAS="lightnovel"
$env:LIGHTNOVEL_RELEASE_KEY_PASSWORD="<你的 key 密码>"

cd android
.\gradlew.bat --no-daemon :app:assembleRelease
```

输出位于 `android/app/build/outputs/apk/release/`。上传前应使用
`apksigner verify --print-certs` 检查证书，并计算 SHA-256。

## GitHub Actions

`.github/workflows/release-android.yml` 通过同名 Repository Secrets 构建签名 APK，
只上传工作流 artifact，不会自动创建 GitHub Release。

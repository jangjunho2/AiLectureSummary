"use client"
import type React from "react"
import { useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Upload } from "lucide-react"
import { useLanguage } from "@/hooks/use-language"
import { motion } from "framer-motion"

export default function VideoUploader() {
  const router = useRouter()
  const { t } = useLanguage()
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  // Drag & Drop 관련 핸들러
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFiles = Array.from(e.dataTransfer.files)
      const videoFiles = droppedFiles.filter(file => file.type.startsWith("video/"))
      setFiles(prevFiles => [
        ...prevFiles,
        ...videoFiles.filter(newFile => 
          !prevFiles.some(existing => 
            existing.name === newFile.name && existing.size === newFile.size
          )
        )
      ])
    }
  }, [])

  // 파일 input 핸들러
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      const newFiles = Array.from(e.target.files).filter(file => 
        file.type.startsWith("video/") && 
        !files.some(existing => 
          existing.name === file.name && existing.size === file.size
        )
      )
      setFiles(prev => [...prev, ...newFiles])
    }
  }, [files])

  // 업로드 핸들러
  const handleUpload = useCallback(async () => {
    if (!files.length) return

    setUploading(true)
    setProgress(0)

    try {
      const formData = new FormData()
      formData.append('file', files[0])

      const response = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()

        // 프로그레스 이벤트
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            setProgress(Math.round((event.loaded / event.total) * 100))
          }
        })

        xhr.onreadystatechange = () => {
          if (xhr.readyState === 4) {
            try {
              if (xhr.status >= 200 && xhr.status < 300) {
                const result = JSON.parse(xhr.responseText)
                // 서버 응답 구조에 따라 키를 맞춰줌
                resolve({
                  aiSummary: result.ai_summary ?? result.aiSummary,
                  originalText: result.original_text ?? result.originalText
                })
              } else {
                // 서버 에러 메시지 추출
                let message = xhr.statusText
                try {
                  const errorJson = JSON.parse(xhr.responseText)
                  if (errorJson.message) message = errorJson.message
                } catch (e) {}
                reject(new Error(message))
              }
            } catch (e) {
              reject(new Error('응답 파싱 실패'))
            }
          }
        }

        xhr.onerror = () => {
          reject(new Error('네트워크 오류'))
        }

        xhr.open('POST', 'http://localhost:8080/api/lecture/upload')
        xhr.send(formData)
      })

      // 결과 페이지로 이동
      const encodedData = encodeURIComponent(JSON.stringify(response))
      router.push(`/summary/demo-result?data=${encodedData}`)

    } catch (error: any) {
      alert(t("upload_failed") + (error?.message ? `: ${error.message}` : ""))
      console.error('Upload Error:', error)
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }, [files, router, t])

  return (
    <div className="w-full">
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center ${
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/20"
        } transition-colors`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center justify-center gap-4">
          <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}>
            <div className="w-20 h-20 rounded-full bg-gradient-to-r from-pink-500 to-orange-500 flex items-center justify-center">
              <Upload className="h-10 w-10 text-white" />
            </div>
          </motion.div>
          <div>
            <h3 className="text-lg font-medium">{t("upload_video")}</h3>
            <p className="text-sm text-muted-foreground mt-1">{t("drag_drop")}</p>
          </div>

          <input 
            type="file" 
            id="video-upload" 
            className="hidden" 
            accept="video/*" 
            onChange={handleFileChange}
            multiple
          />
          <label htmlFor="video-upload">
            <Button 
              variant="outline" 
              className="cursor-pointer rounded-full px-6 bg-background dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              asChild
            >
              <span>{t("select_file")}</span>
            </Button>
          </label>
        </div>
      </div>

      {files.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium mb-2">
            {files.map((file) => (
              <span key={file.name} className="block">
                {file.name} ({(file.size / (1024 * 1024)).toFixed(2)}MB)
              </span>
            ))}
          </p>

          {uploading ? (
            <div className="space-y-2">
              <Progress value={progress} className="h-2 rounded-full" />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>업로드 진행률: {progress}%</span>
                <span>{progress === 100 ? "처리 중..." : "업로드 중"}</span>
              </div>
            </div>
          ) : (
            <Button
              onClick={handleUpload}
              className="w-full mt-2 rounded-full bg-gradient-to-r from-pink-500 to-orange-500 hover:from-pink-600 hover:to-orange-600 border-0 text-white"
              disabled={uploading}
            >
              {t("start_summary")}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

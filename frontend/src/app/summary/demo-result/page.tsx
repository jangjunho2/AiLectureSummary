"use client"
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { Download, Share2, Bookmark } from "lucide-react"
import Link from "next/link"

interface SummaryData {
  title: string
  aiSummary: string
  originalText: string
  duration: string
  filename: string
  timestamp: string
}

export default function DemoSummaryPage() {
  const router = useRouter()
  const [data, setData] = useState<SummaryData>({
    title: "제목 없음",
    aiSummary: "",
    originalText: "",
    duration: "0:00",
    filename: "파일 없음",
    timestamp: "시간 정보 없음"
  })

  useEffect(() => {
    const parseQueryParams = () => {
      const searchParams = new URLSearchParams(window.location.search)
      const encodedData = searchParams.get('data')
      
      if (encodedData) {
        try {
          const decodedData = decodeURIComponent(encodedData)
          const result = JSON.parse(decodedData)
          
          setData({
            title: result.title || "제목 없음",
            aiSummary: result.aiSummary || result.ai_summary || "",
            originalText: result.originalText || result.original_text || "",
            duration: result.duration ? formatDuration(result.duration) : "0:00",
            filename: result.filename || "파일 없음",
            timestamp: result.timestamp 
              ? new Date(result.timestamp).toLocaleString('ko-KR', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })
              : "시간 정보 없음"
          })
        } catch (error) {
          console.error('데이터 파싱 오류:', error)
          router.push('/error')
        }
      }
    }

    const formatDuration = (seconds: number) => {
      if (isNaN(seconds)) return "0:00"
      const minutes = Math.floor(seconds / 60)
      const remainingSeconds = Math.floor(seconds % 60)
      return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
    }

    parseQueryParams()
  }, [router])

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <Link href="/" className="text-blue-600 hover:underline mb-4 inline-block">
            ← 홈으로 돌아가기
          </Link>
          <h1 className="text-3xl font-bold tracking-tight mb-2">{data.title}</h1>
          <div className="text-gray-500 space-y-1">
            <p>파일명: {data.filename}</p>
            <p>동영상 길이: {data.duration} • 처리 시간: {data.timestamp}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
          <div className="md:col-span-2">
            <div className="aspect-video bg-gray-100 rounded-lg mb-4 flex items-center justify-center">
              <span className="text-gray-400">동영상 미리보기</span>
            </div>
          </div>
          <div>
            <Card>
              <CardContent className="p-6">
                <h3 className="text-lg font-medium mb-4">기능 메뉴</h3>
                <div className="space-y-3">
                  <button className="w-full flex items-center gap-2 p-2 rounded border hover:bg-gray-50">
                    <Download size={16} />
                    PDF 저장
                  </button>
                  <button className="w-full flex items-center gap-2 p-2 rounded border hover:bg-gray-50">
                    <Share2 size={16} />
                    공유하기
                  </button>
                  <button className="w-full flex items-center gap-2 p-2 rounded border hover:bg-gray-50">
                    <Bookmark size={16} />
                    북마크
                  </button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        <Tabs defaultValue="summary" className="mb-12">
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="summary">AI 요약</TabsTrigger>
            <TabsTrigger value="original">원문 보기</TabsTrigger>
          </TabsList>

          <TabsContent value="summary">
            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-bold mb-4">생성된 요약</h2>
                <div className="space-y-4">
                  {data.aiSummary.split('\n').map((line, index) => (
                    <p key={index} className="text-gray-700">{line}</p>
                  ))}
                  {!data.aiSummary && (
                    <p className="text-gray-400">요약 데이터가 없습니다.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="original">
            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-bold mb-4">원본 텍스트</h2>
                <div className="whitespace-pre-wrap bg-gray-50 p-4 rounded max-h-[500px] overflow-y-auto">
                  {data.originalText || (
                    <span className="text-gray-400">원문 데이터가 없습니다.</span>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <div className="text-center">
          <h2 className="text-2xl font-bold mb-4">새로운 요약 생성하기</h2>
          <div className="flex justify-center gap-4">
            <Link href="/upload">
              <button className="bg-blue-600 text-white px-6 py-2 rounded-full hover:bg-blue-700 transition-colors">
                동영상 업로드
              </button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

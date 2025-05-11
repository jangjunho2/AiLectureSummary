package com.ktnu.AiLectureSummary.service;


import com.ktnu.AiLectureSummary.domain.Lecture;
import com.ktnu.AiLectureSummary.dto.lecture.LectureRegisterRequest;
import com.ktnu.AiLectureSummary.dto.lecture.LectureResponse;
import com.ktnu.AiLectureSummary.exception.ExternalApiException;
import com.ktnu.AiLectureSummary.exception.FileProcessingException;
import com.ktnu.AiLectureSummary.repository.LectureRepository;
import com.ktnu.AiLectureSummary.util.MultipartFileResource;
import lombok.RequiredArgsConstructor;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.Optional;

@Service
@RequiredArgsConstructor
public class LectureService {
    private final LectureRepository lectureRepository;

    // Client -> Spring -> FastAPI -> Spring&DB -> Client

    /**
     * 업로드된 비디오 파일을 해싱하여 중복 여부를 검사하고,
     * FastAPI 서버에 전송하여 요약 정보를 받은 후, 이를 DB에 저장한다.
     *
     * @param file 사용자가 업로드한 비디오 파일
     * @return 요약된 강의 정보를 담은 응답 객체
     */
    public LectureResponse processVideoUpload(MultipartFile file) {
        validateVideoFile(file);

        // VideoHasing & DB에 중복되는 영상이 존재하는지 확인
        String videoHash = VideoHashing(file);
        Optional<Lecture> optionalLecture = lectureRepository.findByHash(videoHash);

        // 이미 존재하는 경우 바로 바로 반환
        if (optionalLecture.isPresent()) {
            return LectureResponse.from(optionalLecture.get());
        }

        // FastAPI 호출
        LectureRegisterRequest registerRequest =sendToAi(file);

        // DB에 내용 저장
        Lecture saved=lectureRepository.save(Lecture.from(registerRequest, videoHash));

        return LectureResponse.from(saved);

    }

    /**
     * 업로드된 비디오 파일을 FastAPI 서버로 전송하고,
     * 요약 정보를 LectureRegisterRequest 형태로 반환한다.
     * 동기 처리 방식으로 타임아웃이 발생할 수 있다.
     *
     * @param file 전송할 비디오 파일
     * @return 요약 정보가 담긴 요청 객체
     * @throws ExternalApiException FastAPI 요청 중 오류가 발생한 경우
     */
    private LectureRegisterRequest sendToAi(MultipartFile file) {
        // Spring에서 외부 HTTP 요청을 보낼 수 있는 기본 클라이언트
        RestTemplate restTemplate = new RestTemplate();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3000); // 연결 타임아웃: 3초
        factory.setReadTimeout(100000); // 응답 타임 아웃: 100초
        restTemplate.setRequestFactory(factory);

        // 요청 헤더 설정, FastAPI가 multipart 형식으로 파일을 받을 수 있게 Content-Type을 multipart/form-data로 지정
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        // 하나의 key에 여러 개의 value를 가질 수 있는 Map, multipart 요청에서는 "file" 같은 form 필드명을 키로 설정해야 함
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        try {
            // FastAPI 파라미터 이름 == Spring 쪽 key 일치해야 동작? "file"
            //  Spring 서버가 FastAPI 서버에 파일을 전송하기 위해 multipart/form-data 요청 본문(body)을 구성
            body.add("file", new MultipartFileResource(file.getInputStream(), file.getOriginalFilename()));
        } catch (IOException e) {
            throw new FileProcessingException("FastAPI 전송 중 파일 읽기 실패", e);
        }
        //  Spring에서 FastAPI로 파일을 보내기 위한 HTTP 요청 객체(requestEntity)를 구성하는 부분
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // 동기식 처리로 fastAPI에서 요청을 계속 기다림
        try {
            ResponseEntity<LectureRegisterRequest> response = restTemplate.exchange(
                    "http://ai:9090/api/summary",  // FastAPI 엔드포인트
                    HttpMethod.POST,
                    requestEntity,
                    LectureRegisterRequest.class // 받은 json 응답을 역직렬화
            );
            if (response.getBody() == null) {
                throw new ExternalApiException("FastAPI 응답이 비어 있습니다.");
            }

            return response.getBody();
        } catch (ResourceAccessException e) {
            // 타임아웃 or 연결 실패
            throw new ExternalApiException("FastAPI 서버와의 연결이 실패했거나 응답 시간이 초과되었습니다.", e);

        } catch (HttpStatusCodeException e) {
            // FastAPI 응답이 400, 500 에러일 때
            String errorBody = e.getResponseBodyAsString();
            throw new ExternalApiException("FastAPI 응답 오류: " + errorBody, e);

        } catch (Exception e) {
            throw new ExternalApiException("FastAPI 요청 중 알 수 없는 오류 발생", e);
        }
    }

    /**
     * 비디오 파일을 SHA-256 해시 알고리즘으로 해싱하여 고유 문자열을 생성한다.
     *
     * @param file 해싱할 비디오 파일
     * @return Base64로 인코딩된 해시 문자열
     * @throws RuntimeException 파일 읽기 실패 또는 해시 처리 실패 시
     */
    private String VideoHashing(MultipartFile file) {
        // 비디오 해싱
        try (InputStream inputStream = file.getInputStream()) {
            // SHA-256 해시 알고리즘 계산기 객체 생성
            MessageDigest digest = MessageDigest.getInstance("SHA-256");

            // 8KB씩 파일을 읽기 위한 버퍼 생성
            byte[] buffer = new byte[8192];

            int bytesRead;
            while ((bytesRead = inputStream.read(buffer)) != -1) { // 파일 끝이면 InputStream.read()는 파일 끝이 끝이면 -1 을 반환
                // 읽은 데이터를 해시 계산에 누적
                digest.update(buffer, 0, bytesRead);
            }

            // 전체 파일을 읽은 뒤 최종 해시 계산
            byte[] hashBytes = digest.digest();

            // 이진 데이터-> 문자열 형태의 해시값으로 리턴
            return Base64.getEncoder().encodeToString(hashBytes);
        } catch (IOException | NoSuchAlgorithmException e) {
            throw new RuntimeException("비디오 해싱 실패", e);
        }
    }


    private void validateVideoFile(MultipartFile file) {
        // 파일 확장자는 사용자가 쉽게 변경할 수 있으므로 신뢰할 수 없음
        // MIME 타입(Content-Type)을 기반으로 파일 형식을 검증함
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("파일이 비어 있습니다.");
        }
        String contentType = file.getContentType();
        if (contentType == null || !contentType.startsWith("video/")) {
            throw new IllegalArgumentException("지원하지 않는 파일 형식입니다. 비디오 파일만 업로드 가능합니다.");
        }
    }
    // 비디오 삭제?


}

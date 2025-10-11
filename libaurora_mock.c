#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
  #define API __declspec(dllexport)
#else
  #define API
#endif

typedef struct { int w,h; float fps; } EncCtx;
typedef struct { int d; } DecCtx;

API int aurora_version(void){ return 1; }

API void* aurora_encoder_create(int w,int h,float fps){
  EncCtx* c = (EncCtx*)malloc(sizeof(EncCtx));
  if(!c) return NULL; c->w=w; c->h=h; c->fps=fps; return c;
}

API int aurora_encoder_encode(void* enc,
  const uint8_t* y, const uint8_t* u, const uint8_t* v,
  int ys, int us, int vs,
  uint8_t* out, size_t cap, size_t* out_size)
{
  EncCtx* c = (EncCtx*)enc; if(!c) return -1;
  int w=c->w, h=c->h; size_t Y=(size_t)w*h, U=(size_t)(w/2)*(h/2), V=U;
  size_t need = 16 + Y + U + V; if(cap < need) return -2;
  memcpy(out+0,  &w,   4); memcpy(out+4, &h, 4); memcpy(out+8, &c->fps, 4); memset(out+12, 0, 4);
  uint8_t* p = out+16;
  for(int r=0;r<h;++r){ memcpy(p, y+(size_t)r*ys, (size_t)w); p+=w; }
  for(int r=0;r<h/2;++r){ memcpy(p, u+(size_t)r*us, (size_t)(w/2)); p+=(w/2); }
  for(int r=0;r<h/2;++r){ memcpy(p, v+(size_t)r*vs, (size_t)(w/2)); p+=(w/2); }
  *out_size = (size_t)(p - out);
  return 0;
}

API void  aurora_encoder_free(void* enc){ if(enc) free(enc); }

API void* aurora_decoder_create(void){ return malloc(sizeof(DecCtx)); }

API int   aurora_decoder_decode(void* dec, const uint8_t* bs, size_t n,
  uint8_t* y, uint8_t* u, uint8_t* v,
  int ys, int us, int vs, int* ow, int* oh, float* ofps)
{
  if(!dec || !bs || n < 16) return -1;
  int w=*(const int*)(bs+0), h=*(const int*)(bs+4); float fps=*(const float*)(bs+8);
  size_t Y=(size_t)w*h, U=(size_t)(w/2)*(h/2), V=U;
  if(n < 16+Y+U+V) return -2;
  const uint8_t* p=bs+16;
  for(int r=0;r<h;++r){ memcpy(y+(size_t)r*ys, p, (size_t)w); p+=w; }
  for(int r=0;r<h/2;++r){ memcpy(u+(size_t)r*us, p, (size_t)(w/2)); p+=(w/2); }
  for(int r=0;r<h/2;++r){ memcpy(v+(size_t)r*vs, p, (size_t)(w/2)); p+=(w/2); }
  *ow=w; *oh=h; *ofps=fps; return 0;
}

API void aurora_decoder_free(void* dec){ if(dec) free(dec); }

#ifndef NULLPTR_H
#define NULLPTR_H

// define nullptr to be NULL to support C++ standards before C++11
#if __cplusplus < 201103L
  #define nullptr NULL
#endif

#endif // NULLPTR_H

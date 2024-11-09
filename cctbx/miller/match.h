#ifndef CCTBX_MILLER_MATCH_H
#define CCTBX_MILLER_MATCH_H

#include <scitbx/array_family/shared.h>
#include <cctbx/import_scitbx_af.h>
#include <functional>
#include <cmath>

namespace cctbx { namespace miller {

  typedef af::tiny<std::size_t, 2> pair_type;

  namespace detail {

    template <typename NumType>
    struct additive_sigma
    {
      using first_argument_type = NumType;
      using second_argument_type = NumType;
      using result_type = NumType;

      NumType operator()(NumType const& x, NumType const& y)
      {
        return std::sqrt(x*x + y*y);
      }
    };

    template <typename NumType>
    struct average
    {
      using first_argument_type = NumType;
      using second_argument_type = NumType;
      using result_type = NumType;

      NumType operator()(NumType const& x, NumType const& y)
      {
        return (x + y) / NumType(2);
      }
    };

    template <typename Op>
    struct pair_op
    {
      using second_argument_type = typename Op::second_argument_type;
      using first_argument_type = typename Op::first_argument_type;
      using result_type = typename Op::result_type;

      explicit pair_op(af::const_ref<pair_type> const& pairs)
      : pairs_(pairs)
      {}

      af::shared<result_type>
      operator()(
        af::const_ref<first_argument_type> const& a0,
        af::const_ref<second_argument_type> const& a1) const
      {
        af::shared<result_type> result((af::reserve(pairs_.size())));
        for(std::size_t i=0;i<pairs_.size();i++) {
          result.push_back(Op()(a0[pairs_[i][0]], a1[pairs_[i][1]]));
        }
        return result;
      }

      af::const_ref<pair_type> pairs_;
    };

  } // namespace detail

}} // namespace cctbx::miller

#endif // CCTBX_MILLER_MATCH_H
